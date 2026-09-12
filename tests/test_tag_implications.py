import asyncio
import unittest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.enums import FileTypeEnum, RatingEnum, TagCategoryEnum
from backend.app.models import Media, Tag, TagAlias, TagImplication, User
from backend.app.redis_client import redis_cache
from backend.app.routes.media import bulk_update_tags, preview_or_create_tags
from backend.app.routes.tags import batch_resolve_combined_tags
from backend.app.schemas import (
    BatchResolveCombinedItem,
    BatchResolveCombinedRequest,
    BulkTagUpdateItem,
    BulkTagUpdateRequest,
)
from backend.app.routes.tag_implications import (
    _clean_patterns,
    _resolve_tag_names,
    create_implication,
    delete_implication,
    expand_tag_implications,
    list_implications,
    simulate_apply_all_implications,
    update_implication,
    ExpandImplicationsRequest,
    TagImplicationCreate,
)
from backend.app.utils.tag_utils import expand_implications, resolve_implications
from tests.backup_test_base import BackupTestBase

class TestTagImplications(BackupTestBase):
    """
    Comprehensive test suite for the Tag Implications subsystem, covering:
    - Pattern normalization and tag resolving helpers
    - Admin CRUD API endpoints (/api/tag-implications)
    - Duplicate detection and boundary conditions
    - Recursive expansion and cycle safety in tag_utils
    - Bulk simulation route (/simulate-apply-all)
    - Tag creation and dry-run integration in media workflow
    - Database cascades and orphaned entity cleanup
    """

    def setUp(self):
        super().setUp()
        self.old_redis_enabled = redis_cache._enabled
        redis_cache._enabled = False

        self.admin_user = User(id=1, username="admin", password_hash="hash")
        self.db.add(self.admin_user)
        self.db.commit()

        # Seed standard test tags
        self.tag_cat = self._create_tag("cat")
        self.tag_animal = self._create_tag("animal")
        self.tag_feline = self._create_tag("feline")
        self.tag_kitten = self._create_tag("kitten")
        self.tag_mammal = self._create_tag("mammal")
        self.tag_1girl = self._create_tag("1girl")
        self.tag_solo = self._create_tag("solo")
        self.tag_long_hair = self._create_tag("long_hair")
        self.tag_animated = self._create_tag("animated")
        self.tag_animated_gif = self._create_tag("animated_gif")
        self.tag_fox_tail = self._create_tag("fox_tail")
        self.tag_tail = self._create_tag("tail")
        self.db.commit()

    def tearDown(self):
        redis_cache._enabled = self.old_redis_enabled
        super().tearDown()

    def _create_tag(self, name: str, category: TagCategoryEnum = TagCategoryEnum.general, post_count: int = 0) -> Tag:
        """Helper to create and persist a Tag model."""
        tag = Tag(name=name, category=category, post_count=post_count)
        self.db.add(tag)
        self.db.flush()
        return tag

    def _create_media(self, filename: str, rating: RatingEnum = RatingEnum.safe) -> Media:
        """Helper to create and persist a Media item."""
        media = Media(
            hash=f"hash_{filename}",
            filename=filename,
            path=f"media/original/{filename}",
            file_type=FileTypeEnum.image,
            file_size=1024,
            width=100,
            height=100,
            rating=rating,
        )
        self.db.add(media)
        self.db.flush()
        return media

    # Helper & Validation Tests
    def test_clean_patterns_normalization(self):
        """Test pattern list normalization: lowercasing, trimming, deduplicating, and dropping empties."""
        raw = ["  *TAIL  ", "*tail", "  ", "", "GIF*", "gif*"]
        cleaned = _clean_patterns(raw)
        self.assertEqual(cleaned, ["*tail", "gif*"])

    def test_clean_patterns_empty_or_none(self):
        """Test that _clean_patterns safely handles None and empty input lists."""
        self.assertEqual(_clean_patterns(None), [])
        self.assertEqual(_clean_patterns([]), [])

    def test_resolve_tag_names_success(self):
        """Test resolving tag objects by name with mixed casing and leading/trailing whitespace."""
        tags = _resolve_tag_names(self.db, ["  CAT  ", "Animal"])
        self.assertEqual(len(tags), 2)
        self.assertEqual({t.name for t in tags}, {"cat", "animal"})

    def test_resolve_tag_names_not_found(self):
        """Test resolving an unknown tag name raises HTTP 400 Bad Request."""
        with self.assertRaises(HTTPException) as ctx:
            _resolve_tag_names(self.db, ["cat", "non_existent_tag_xyz"])
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("non_existent_tag_xyz", ctx.exception.detail)

    # CRUD Route Tests
    def test_create_implication_with_target_tags(self):
        """Test creating a tag implication with target tags only."""
        data = TagImplicationCreate(
            target_tags=["cat"],
            target_tag_patterns=[],
            implied_tags=["animal", "feline"]
        )
        res = asyncio.run(create_implication(data, current_user=self.admin_user, db=self.db))
        self.assertIsNotNone(res.id)
        self.assertEqual({t.name for t in res.target_tags}, {"cat"})
        self.assertEqual({t.name for t in res.implied_tags}, {"animal", "feline"})
        self.assertEqual(res.target_tag_patterns, [])

        db_imp = self.db.query(TagImplication).filter(TagImplication.id == res.id).first()
        self.assertIsNotNone(db_imp)
        self.assertEqual(len(db_imp.target_tags), 1)
        self.assertEqual(len(db_imp.implied_tags), 2)

    def test_create_implication_with_patterns_only(self):
        """Test creating a tag implication using only target pattern strings."""
        data = TagImplicationCreate(
            target_tags=[],
            target_tag_patterns=["*_tail"],
            implied_tags=["tail"]
        )
        res = asyncio.run(create_implication(data, current_user=self.admin_user, db=self.db))
        self.assertIsNotNone(res.id)
        self.assertEqual(res.target_tags, [])
        self.assertEqual(res.target_tag_patterns, ["*_tail"])
        self.assertEqual({t.name for t in res.implied_tags}, {"tail"})

    def test_create_implication_with_targets_and_patterns(self):
        """Test creating a tag implication containing both target tags and pattern strings."""
        data = TagImplicationCreate(
            target_tags=["solo"],
            target_tag_patterns=["*girl*"],
            implied_tags=["1girl"]
        )
        res = asyncio.run(create_implication(data, current_user=self.admin_user, db=self.db))
        self.assertEqual({t.name for t in res.target_tags}, {"solo"})
        self.assertEqual(res.target_tag_patterns, ["*girl*"])
        self.assertEqual({t.name for t in res.implied_tags}, {"1girl"})

    def test_implication_validation_errors(self):
        """Test validation error cases when target tags or implied tags are missing."""
        # Validation thrown error when either target_tags or target_tag_parrents are provided
        with self.assertRaises(ValidationError) as ctx:
            data_no_targets = TagImplicationCreate(
                target_tags=[],
                target_tag_patterns=[],
                implied_tags=["animal"]
            )
    
        # No implied tags provided
        with self.assertRaises(ValidationError) as ctx:
            data_no_implied = TagImplicationCreate(
                target_tags=["cat"],
                target_tag_patterns=[],
                implied_tags=[]
            )

    def test_list_implications(self):
        """Test listing all implications returns formatted records and normalizes patterns to list."""
        imp1 = TagImplication(
            target_tags=[self.tag_cat],
            target_tag_patterns=None,
            implied_tags=[self.tag_animal]
        )
        imp2 = TagImplication(
            target_tags=[],
            target_tag_patterns=["*_tail"],
            implied_tags=[self.tag_tail]
        )
        self.db.add_all([imp1, imp2])
        self.db.commit()

        results = asyncio.run(list_implications(current_user=self.admin_user, db=self.db))
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertIsInstance(r.target_tag_patterns, list)

    def test_list_implications_pagination_and_search(self):
        """Test pagination and search parameters on list_implications."""
        from fastapi import Response
        tag1 = self._create_tag("page_tag_1")
        tag2 = self._create_tag("page_tag_2")
        tag3 = self._create_tag("search_alpha")
        tag_out = self._create_tag("common_out")

        self.db.add_all([
            TagImplication(target_tags=[tag1], implied_tags=[tag_out]),
            TagImplication(target_tags=[tag2], implied_tags=[tag_out]),
            TagImplication(target_tags=[tag3], implied_tags=[tag_out]),
        ])
        self.db.commit()

        # Test limit and X-Total-Count
        resp = Response()
        res_limit = asyncio.run(list_implications(limit=2, offset=0, response=resp, current_user=self.admin_user, db=self.db))
        self.assertEqual(len(res_limit), 2)
        self.assertIn("X-Total-Count", resp.headers)
        total = int(resp.headers["X-Total-Count"])
        self.assertGreaterEqual(total, 3)

        # Test search
        res_search = asyncio.run(list_implications(search="search_alpha", current_user=self.admin_user, db=self.db))
        self.assertEqual(len(res_search), 1)
        self.assertEqual(res_search[0].target_tags[0].name, "search_alpha")

    def test_list_implications_cleans_orphaned_entities(self):
        """Test list_implications purges implications left empty after target tag deletion."""
        temp_tag = self._create_tag("temp_target")
        self.db.commit()

        imp = TagImplication(
            target_tags=[temp_tag],
            target_tag_patterns=None,
            implied_tags=[self.tag_animal]
        )
        self.db.add(imp)
        self.db.commit()
        imp_id = imp.id

        # Delete target tag, leaving the implication orphaned
        self.db.delete(temp_tag)
        self.db.commit()

        results = asyncio.run(list_implications(current_user=self.admin_user, db=self.db))
        self.assertFalse(any(r.id == imp_id for r in results))
        self.assertIsNone(self.db.query(TagImplication).filter(TagImplication.id == imp_id).first())

    def test_update_implication_success(self):
        """Test updating an existing implication's targets, patterns, and implied tags."""
        imp = TagImplication(
            target_tags=[self.tag_cat],
            target_tag_patterns=None,
            implied_tags=[self.tag_animal]
        )
        self.db.add(imp)
        self.db.commit()

        update_data = TagImplicationCreate(
            target_tags=["kitten"],
            target_tag_patterns=["kit*"],
            implied_tags=["cat", "animal"]
        )
        updated = asyncio.run(update_implication(imp.id, update_data, current_user=self.admin_user, db=self.db))
        self.assertEqual(updated.id, imp.id)
        self.assertEqual({t.name for t in updated.target_tags}, {"kitten"})
        self.assertEqual(updated.target_tag_patterns, ["kit*"])
        self.assertEqual({t.name for t in updated.implied_tags}, {"cat", "animal"})

    def test_update_implication_not_found(self):
        """Test updating a non-existent implication raises HTTP 404."""
        update_data = TagImplicationCreate(
            target_tags=["cat"],
            target_tag_patterns=[],
            implied_tags=["animal"]
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(update_implication(99999, update_data, current_user=self.admin_user, db=self.db))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_delete_implication_success(self):
        """Test deleting an implication removes the record from the database."""
        imp = TagImplication(
            target_tags=[self.tag_cat],
            target_tag_patterns=None,
            implied_tags=[self.tag_animal]
        )
        self.db.add(imp)
        self.db.commit()
        imp_id = imp.id

        res = asyncio.run(delete_implication(imp_id, current_user=self.admin_user, db=self.db))
        self.assertEqual(res, {"status": "success"})
        self.assertIsNone(self.db.query(TagImplication).filter(TagImplication.id == imp_id).first())

    def test_delete_implication_not_found(self):
        """Test deleting a non-existent implication raises HTTP 404."""
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(delete_implication(99999, current_user=self.admin_user, db=self.db))
        self.assertEqual(ctx.exception.status_code, 404)

    # Duplicate Detection & False-Positive Boundary Tests
    def test_distinct_implications_with_overlapping_subsets(self):
        """
        Verify distinct implications sharing overlapping subsets of target tags are permitted:
        Rule 1: [1girl, solo] -> [long_hair]
        Rule 2: [1girl] -> [long_hair] (broader, distinct rule)
        """
        imp1 = TagImplication(
            target_tags=[self.tag_1girl, self.tag_solo],
            target_tag_patterns=None,
            implied_tags=[self.tag_long_hair]
        )
        self.db.add(imp1)
        self.db.commit()

        data2 = TagImplicationCreate(
            target_tags=["1girl"],
            target_tag_patterns=[],
            implied_tags=["long_hair"]
        )
        res2 = asyncio.run(create_implication(data2, current_user=self.admin_user, db=self.db))
        self.assertIsNotNone(res2.id)
        self.assertNotEqual(res2.id, imp1.id)

    def test_substring_patterns_distinct(self):
        """
        Verify pattern matching in duplicate checks does not confuse substring occurrences with duplicates:
        Existing: pattern ['animated_gif'] -> [animated]
        New: pattern ['gif'] -> [animated]
        """
        imp1 = TagImplication(
            target_tags=[],
            target_tag_patterns=["animated_gif"],
            implied_tags=[self.tag_animated]
        )
        self.db.add(imp1)
        self.db.commit()

        data2 = TagImplicationCreate(
            target_tags=[],
            target_tag_patterns=["gif"],
            implied_tags=["animated"]
        )
        res2 = asyncio.run(create_implication(data2, current_user=self.admin_user, db=self.db))
        self.assertIsNotNone(res2.id)
        self.assertNotEqual(res2.id, imp1.id)

    def test_pattern_only_vs_target_and_pattern_distinct(self):
        """
        Verify an implication with only patterns is distinct from one with target tags and patterns:
        Existing: target ['solo'] + pattern ['test*'] -> ['blush']
        New: pattern ['test*'] (no target tags) -> ['blush']
        """
        tag_blush = self._create_tag("blush")
        self.db.commit()

        imp1 = TagImplication(
            target_tags=[self.tag_solo],
            target_tag_patterns=["test*"],
            implied_tags=[tag_blush]
        )
        self.db.add(imp1)
        self.db.commit()

        data2 = TagImplicationCreate(
            target_tags=[],
            target_tag_patterns=["test*"],
            implied_tags=["blush"]
        )
        res2 = asyncio.run(create_implication(data2, current_user=self.admin_user, db=self.db))
        self.assertIsNotNone(res2.id)
        self.assertNotEqual(res2.id, imp1.id)

    # Tag Expansion Logic Tests (tag_utils.expand_implications)
    def test_expand_implications_direct_single_tag(self):
        """Test direct single-tag implication expansion (cat -> animal)."""
        imp = TagImplication(
            target_tags=[self.tag_cat],
            target_tag_patterns=None,
            implied_tags=[self.tag_animal]
        )
        self.db.add(imp)
        self.db.commit()

        tag_set = {self.tag_cat.id: self.tag_cat}
        expand_implications(self.db, tag_set)

        self.assertIn(self.tag_animal.id, tag_set)
        self.assertEqual(tag_set[self.tag_animal.id].name, "animal")

    def test_expand_implications_pattern_glob(self):
        """Test glob pattern implication expansion (*_tail -> tail)."""
        imp = TagImplication(
            target_tags=[],
            target_tag_patterns=["*_tail"],
            implied_tags=[self.tag_tail]
        )
        self.db.add(imp)
        self.db.commit()

        tag_set = {self.tag_fox_tail.id: self.tag_fox_tail}
        expand_implications(self.db, tag_set)

        self.assertIn(self.tag_tail.id, tag_set)

    def test_expand_implications_chained_recursive(self):
        """Test recursive multi-step expansion: kitten -> cat -> mammal -> animal."""
        imp1 = TagImplication(target_tags=[self.tag_kitten], implied_tags=[self.tag_cat])
        imp2 = TagImplication(target_tags=[self.tag_cat], implied_tags=[self.tag_mammal])
        imp3 = TagImplication(target_tags=[self.tag_mammal], implied_tags=[self.tag_animal])
        self.db.add_all([imp1, imp2, imp3])
        self.db.commit()

        tag_set = {self.tag_kitten.id: self.tag_kitten}
        expand_implications(self.db, tag_set)

        names = {t.name for t in tag_set.values()}
        self.assertEqual(names, {"kitten", "cat", "mammal", "animal"})

    def test_expand_implications_circular_safety(self):
        """Test that circular implications (a -> b and b -> a) terminate safely without infinite loop."""
        imp1 = TagImplication(target_tags=[self.tag_cat], implied_tags=[self.tag_feline])
        imp2 = TagImplication(target_tags=[self.tag_feline], implied_tags=[self.tag_cat])
        self.db.add_all([imp1, imp2])
        self.db.commit()

        tag_set = {self.tag_cat.id: self.tag_cat}
        expand_implications(self.db, tag_set)

        names = {t.name for t in tag_set.values()}
        self.assertEqual(names, {"cat", "feline"})

    def test_expand_implications_multiple_target_tags(self):
        """Test implication triggering when any of the target tags are present."""
        imp = TagImplication(
            target_tags=[self.tag_kitten, self.tag_cat],
            implied_tags=[self.tag_feline]
        )
        self.db.add(imp)
        self.db.commit()

        tag_set = {self.tag_kitten.id: self.tag_kitten}
        expand_implications(self.db, tag_set)
        self.assertIn(self.tag_feline.id, tag_set)

    def test_expand_implications_empty_inputs(self):
        """Test expand_implications with an empty tag_set or empty database implications."""
        tag_set = {}
        expand_implications(self.db, tag_set)
        self.assertEqual(tag_set, {})

        tag_set = {self.tag_cat.id: self.tag_cat}
        expand_implications(self.db, tag_set)
        self.assertEqual(tag_set, {self.tag_cat.id: self.tag_cat})

    # Media Workflow & Preview Integration Tests
    def test_preview_or_create_tags_with_implications(self):
        """Test that preview_or_create_tags resolves implications during upload tagging."""
        imp = TagImplication(target_tags=[self.tag_kitten], implied_tags=[self.tag_cat, self.tag_animal])
        self.db.add(imp)
        self.db.commit()

        # Dry run preview
        proposed = preview_or_create_tags(self.db, ["kitten"], expand=True, dry_run=True)
        prop_names = {p.name for p in proposed}
        self.assertIn("kitten", prop_names)
        self.assertIn("cat", prop_names)
        self.assertIn("animal", prop_names)

        # Committed creation
        created_tags = preview_or_create_tags(self.db, ["kitten"], expand=True, dry_run=False)
        created_names = {t.name for t in created_tags}
        self.assertIn("kitten", created_names)
        self.assertIn("cat", created_names)
        self.assertIn("animal", created_names)

    # Simulate Apply All Route Tests
    def test_simulate_apply_all_implications(self):
        """Test simulate_apply_all_implications computes added tags across all media."""
        imp = TagImplication(target_tags=[self.tag_cat], implied_tags=[self.tag_animal])
        self.db.add(imp)

        # Media 1: has 'cat', should be affected
        m1 = self._create_media("m1.jpg")
        m1.tags.append(self.tag_cat)

        # Media 2: already has 'animal', should NOT be affected
        m2 = self._create_media("m2.jpg")
        m2.tags.append(self.tag_animal)

        # Media 3: has 'solo', should NOT be affected
        m3 = self._create_media("m3.jpg")
        m3.tags.append(self.tag_solo)
        self.db.commit()

        result = asyncio.run(simulate_apply_all_implications(current_user=self.admin_user, db=self.db))
        affected = result.get("affected_media", [])
        self.assertEqual(len(affected), 1)
        self.assertEqual(affected[0]["media_id"], m1.id)
        self.assertEqual(affected[0]["added_tags"], ["animal"])

    def test_simulate_apply_all_no_implications(self):
        """Test simulate_apply_all_implications returns empty list when no implications exist."""
        result = asyncio.run(simulate_apply_all_implications(current_user=self.admin_user, db=self.db))
        self.assertEqual(result, {"affected_media": []})

    # Database Cascades & Relationship Integrity Tests
    def test_cascade_tag_deletion_removes_association_rows(self):
        """Test deleting a Tag cleans association rows from implication tables."""
        temp_tag = self._create_tag("temp_tag")
        self.db.commit()

        imp = TagImplication(
            target_tags=[temp_tag],
            implied_tags=[self.tag_animal]
        )
        self.db.add(imp)
        self.db.commit()

        self.db.delete(temp_tag)
        self.db.commit()

        self.db.refresh(imp)
        self.assertEqual(len(imp.target_tags), 0)
        self.assertEqual(len(imp.implied_tags), 1)

    def test_cascade_implication_deletion_preserves_tags(self):
        """Test deleting a TagImplication preserves the underlying Tag entities."""
        imp = TagImplication(
            target_tags=[self.tag_cat],
            implied_tags=[self.tag_animal]
        )
        self.db.add(imp)
        self.db.commit()
        imp_id = imp.id

        self.db.delete(imp)
        self.db.commit()

        self.assertIsNotNone(self.db.query(Tag).filter(Tag.name == "cat").first())
        self.assertIsNotNone(self.db.query(Tag).filter(Tag.name == "animal").first())

    # Tag Implication Resolution Tests (resolve_implications & /expand endpoint)
    def test_resolve_implications_chain_hierarchy(self):
        """Verify deep multi-step implication chain resolution."""
        chain = ["wolf", "canine_beast", "quadruped", "vertebrate", "creature"]
        tag_objs = [self._create_tag(name) for name in chain]
        for idx in range(len(tag_objs) - 1):
            self.db.add(TagImplication(target_tags=[tag_objs[idx]], implied_tags=[tag_objs[idx + 1]]))
        self.db.commit()

        # From root of chain, all descendants are returned
        result = resolve_implications(self.db, ["wolf"])
        self.assertEqual(sorted(result), sorted(["canine_beast", "quadruped", "vertebrate", "creature"]))

        # From midpoint of chain, only subsequent descendants are returned
        result_mid = resolve_implications(self.db, ["quadruped"])
        self.assertEqual(sorted(result_mid), sorted(["creature", "vertebrate"]))

    def test_resolve_implications_max_depth_limit(self):
        """Verify max_depth restricts the number of recursive expansion passes."""
        chain = ["husky", "hound", "doggo", "carnivore", "eukaryote"]
        tag_objs = [self._create_tag(name) for name in chain]
        for idx in range(len(tag_objs) - 1):
            self.db.add(TagImplication(target_tags=[tag_objs[idx]], implied_tags=[tag_objs[idx + 1]]))
        self.db.commit()

        # With max_depth=2, husky should expand to hound and doggo, but not carnivore or eukaryote
        limited = resolve_implications(self.db, ["husky"], max_depth=2)
        self.assertEqual(sorted(limited), ["doggo", "hound"])

    def test_resolve_implications_wildcard_patterns_without_targets(self):
        """Verify standalone pattern-based implications match wildcards and imply tags."""
        clothing = self._create_tag("clothing")
        female = self._create_tag("female")

        self.db.add(TagImplication(target_tag_patterns=["*_dress"], implied_tags=[clothing]))
        self.db.add(TagImplication(target_tag_patterns=["?maid"], implied_tags=[female]))
        self.db.commit()

        res = resolve_implications(self.db, ["summer_dress", "1maid"])
        self.assertEqual(sorted(res), ["clothing", "female"])

        # Matching only one pattern implies only that rule's tag
        res_single = resolve_implications(self.db, ["summer_dress"])
        self.assertEqual(res_single, ["clothing"])

    def test_resolve_implications_conjunction_multiple_targets(self):
        """Verify multi-target implications fire only when ALL target tags are present."""
        winter = self._create_tag("winter")
        coat = self._create_tag("coat")
        warm = self._create_tag("warm_clothing")

        self.db.add(TagImplication(target_tags=[winter, coat], implied_tags=[warm]))
        self.db.commit()

        # Incomplete target sets must not trigger the implication
        self.assertEqual(resolve_implications(self.db, ["winter"]), [])
        self.assertEqual(resolve_implications(self.db, ["coat"]), [])

        # Full target set triggers the implication
        self.assertEqual(resolve_implications(self.db, ["winter", "coat"]), ["warm_clothing"])

    def test_resolve_implications_multi_tag_consequence(self):
        """Verify an implication can expand to multiple implied tags in one rule."""
        trigger = self._create_tag("twintails")
        implied1 = self._create_tag("pigtails")
        implied2 = self._create_tag("hairstyle")

        self.db.add(TagImplication(target_tags=[trigger], implied_tags=[implied1, implied2]))
        self.db.commit()

        res = resolve_implications(self.db, ["twintails"])
        self.assertEqual(sorted(res), ["hairstyle", "pigtails"])

    def test_resolve_implications_duplicate_rules_deduplicated(self):
        """Verify convergent rules pointing to the same implied tag produce deduplicated output."""
        puppy = self._create_tag("puppy")
        bunny = self._create_tag("bunny")
        pet = self._create_tag("pet")

        self.db.add(TagImplication(target_tags=[puppy], implied_tags=[pet]))
        self.db.add(TagImplication(target_tags=[bunny], implied_tags=[pet]))
        self.db.commit()

        res = resolve_implications(self.db, ["puppy", "bunny"])
        self.assertEqual(res, ["pet"])

        # If the implied tag is already in input, nothing new should be returned
        res_already_present = resolve_implications(self.db, ["puppy", "bunny", "pet"])
        self.assertEqual(res_already_present, [])

    def test_resolve_implications_hybrid_pattern_and_target(self):
        """Verify rules requiring both explicit target tags and pattern matches."""
        sword = self._create_tag("sword")
        knight = self._create_tag("knight")

        self.db.add(TagImplication(target_tags=[sword], target_tag_patterns=["*_armor"], implied_tags=[knight]))
        self.db.commit()

        # Both present -> matches
        self.assertEqual(resolve_implications(self.db, ["sword", "steel_armor"]), ["knight"])

        # Target present but pattern missing
        self.assertEqual(resolve_implications(self.db, ["sword"]), [])
        self.assertEqual(resolve_implications(self.db, ["sword", "steel_shield"]), [])

        # Pattern present but target missing
        self.assertEqual(resolve_implications(self.db, ["steel_armor"]), [])

    def test_resolve_implications_cycle_safety(self):
        """Verify cyclical implication graphs terminate cleanly without infinite loops."""
        node_a = self._create_tag("cycle_alpha")
        node_b = self._create_tag("cycle_beta")
        node_c = self._create_tag("cycle_gamma")

        self.db.add(TagImplication(target_tags=[node_a], implied_tags=[node_b]))
        self.db.add(TagImplication(target_tags=[node_b], implied_tags=[node_c]))
        self.db.add(TagImplication(target_tags=[node_c], implied_tags=[node_a]))
        self.db.commit()

        res = resolve_implications(self.db, ["cycle_alpha"])
        self.assertEqual(sorted(res), ["cycle_beta", "cycle_gamma"])

    def test_resolve_implications_reflexive_self_reference(self):
        """Verify self-implicating rules (e.g. tag implies itself) do not yield new tags."""
        stand = self._create_tag("standalone_tag")
        self.db.add(TagImplication(target_tags=[stand], implied_tags=[stand]))
        self.db.commit()

        self.assertEqual(resolve_implications(self.db, ["standalone_tag"]), [])

    def test_resolve_implications_empty_and_unknown_inputs(self):
        """Verify empty lists, whitespace, or unrecognized tags return an empty list gracefully."""
        self.assertEqual(resolve_implications(self.db, []), [])
        self.assertEqual(resolve_implications(self.db, ["", "   "]), [])
        self.assertEqual(resolve_implications(self.db, ["nonexistent_tag_xyz"]), [])

    def test_expand_implications_api_endpoint(self):
        """Verify the POST /api/tag-implications/expand route returns expected implied tags."""
        tabby = self._create_tag("tabby")
        hunter = self._create_tag("hunter")
        self.db.add(TagImplication(target_tags=[tabby], implied_tags=[hunter]))
        self.db.commit()

        payload = ExpandImplicationsRequest(tags=["tabby"])
        res = asyncio.run(expand_tag_implications(payload, current_user=self.admin_user, db=self.db))
        self.assertEqual(res, {"implied_tags": ["hunter"]})

        empty_payload = ExpandImplicationsRequest(tags=[])
        empty_res = asyncio.run(expand_tag_implications(empty_payload, current_user=self.admin_user, db=self.db))
        self.assertEqual(empty_res, {"implied_tags": []})

    def test_simulate_apply_all_large_scale(self):
        """Verify simulate_apply_all_implications performs efficiently with large rule sets."""
        import time

        # Create a hierarchy of tags and implications
        root_tags = [self._create_tag(f"root_{i}") for i in range(200)]
        child_tags = [self._create_tag(f"child_{i}") for i in range(200)]
        grandchild_tags = [self._create_tag(f"grandchild_{i}") for i in range(200)]

        implications = []
        for i in range(200):
            implications.append(TagImplication(target_tags=[root_tags[i]], implied_tags=[child_tags[i]]))
            implications.append(TagImplication(target_tags=[child_tags[i]], implied_tags=[grandchild_tags[i]]))
        self.db.add_all(implications)

        # Create media items that have root tags
        media_items = []
        for i in range(100):
            m = self._create_media(f"large_scale_{i}.jpg")
            m.tags.append(root_tags[i])
            media_items.append(m)
        self.db.commit()

        start = time.perf_counter()
        result = asyncio.run(simulate_apply_all_implications(current_user=self.admin_user, db=self.db))
        duration = time.perf_counter() - start

        affected = result.get("affected_media", [])
        self.assertEqual(len(affected), 100)
        # Each media item with root_i should get both child_i and grandchild_i
        self.assertEqual(affected[0]["added_tags"], [f"child_0", f"grandchild_0"])
        # Performance check: 100 media with 400 chained implications should simulate well under 0.5s
        self.assertLess(duration, 0.5)

    def test_batch_resolve_combined_tags(self):
        """Verify POST /api/tags/batch-resolve-combined resolves aliases and implications on combined tags."""
        girl = self._create_tag("girl")
        blonde_hair = self._create_tag("blonde_hair")
        blue_eyes = self._create_tag("blue_eyes")
        swimsuit = self._create_tag("swimsuit")
        summer = self._create_tag("summer")
        blue_eyed_girl = self._create_tag("blue_eyed_girl")

        # Alias: blonde -> blonde_hair
        self.db.add(TagAlias(alias_name="blonde", target_tag_id=blonde_hair.id))
        # Alias: golden_hair -> blonde_hair
        self.db.add(TagAlias(alias_name="golden_hair", target_tag_id=blonde_hair.id))
        # Implication: swimsuit -> summer
        self.db.add(TagImplication(target_tags=[swimsuit], implied_tags=[summer]))
        # Conjunction implication: girl + blue_eyes -> blue_eyed_girl
        self.db.add(TagImplication(target_tags=[girl, blue_eyes], implied_tags=[blue_eyed_girl]))
        self.db.commit()

        # Item 1: initial has 'girl' and aliased 'blonde'.
        # new_tags has:
        # - valid tags: 'blue_eyes', 'swimsuit'
        # - valid alias: 'golden_hair' (resolves to 'blonde_hair')
        # - invalid/non-existent tags: 'fake_tag_123', 'blurred_background_effect', 'random_word'
        req = BatchResolveCombinedRequest(
            items=[
                BatchResolveCombinedItem(
                    id=101,
                    current_tags=["girl", "blonde"],
                    new_tags=["blue_eyes", "swimsuit", "golden_hair", "fake_tag_123", "blurred_background_effect", "random_word"],
                ),
                BatchResolveCombinedItem(
                    id=102,
                    current_tags=["girl"],
                    new_tags=["non_existent_prose_phrase"],
                ),
            ]
        )

        res = asyncio.run(batch_resolve_combined_tags(req, db=self.db))
        results = res["results"]

        item101 = results["101"]
        # Initial tags should have alias resolved
        self.assertEqual(item101["current_tags"], ["girl", "blonde_hair"])
        # Combined new_tags must include initial tags, valid new tags, and implied tags
        self.assertIn("girl", item101["new_tags"])
        self.assertIn("blonde_hair", item101["new_tags"])
        self.assertIn("blue_eyes", item101["new_tags"])
        self.assertIn("swimsuit", item101["new_tags"])
        self.assertIn("blue_eyed_girl", item101["new_tags"])
        self.assertIn("summer", item101["new_tags"])

        # Non-existent tags MUST NOT be included
        self.assertNotIn("fake_tag_123", item101["new_tags"])
        self.assertNotIn("blurred_background_effect", item101["new_tags"])
        self.assertNotIn("random_word", item101["new_tags"])
        self.assertNotIn("fake_tag_123", item101["added_tags"])
        self.assertNotIn("blurred_background_effect", item101["added_tags"])
        self.assertNotIn("random_word", item101["added_tags"])

        # added_tags must only include tags NOT in original initial tags
        self.assertNotIn("girl", item101["added_tags"])
        self.assertNotIn("blonde_hair", item101["added_tags"])
        self.assertIn("blue_eyes", item101["added_tags"])
        self.assertIn("swimsuit", item101["added_tags"])
        self.assertIn("blue_eyed_girl", item101["added_tags"])
        self.assertIn("summer", item101["added_tags"])

        # Item 102 only had non-existent tags in new_tags, so added_tags is empty and new_tags equals current_tags
        item102 = results["102"]
        self.assertEqual(item102["current_tags"], ["girl"])
        self.assertEqual(item102["new_tags"], ["girl"])
        self.assertEqual(item102["added_tags"], [])

    def test_bulk_update_tags_expands_implications(self):
        """Verify bulk_update_tags applies implications when saving."""
        swimsuit = self._create_tag("swimsuit_bulk")
        summer = self._create_tag("summer_bulk")
        self.db.add(TagImplication(target_tags=[swimsuit], implied_tags=[summer]))
        self.db.commit()

        media = self._create_media("test_bulk_imp.jpg")
        self.db.commit()

        req = BulkTagUpdateRequest(
            items=[
                BulkTagUpdateItem(id=media.id, tags=["swimsuit_bulk"])
            ]
        )
        res = asyncio.run(bulk_update_tags(req, current_user=self.admin_user, db=self.db))
        self.assertEqual(res.updated_count, 1)

        # Verify media now has both swimsuit_bulk and implied summer_bulk
        self.db.refresh(media)
        assigned_tag_names = {t.name for t in media.tags}
        self.assertIn("swimsuit_bulk", assigned_tag_names)
        self.assertIn("summer_bulk", assigned_tag_names)

if __name__ == "__main__":
    unittest.main()
