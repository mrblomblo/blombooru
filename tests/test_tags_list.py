import asyncio

from backend.app.enums import TagCategoryEnum
from backend.app.models import Tag, TagAlias, User
from backend.app.routes.tags import get_tags_list
from tests.test_base import BackupTestBase

class TestTagsList(BackupTestBase):
    """Covers the /api/tags/list filtering, sorting, paging and payload shape."""

    def setUp(self):
        super().setUp()
        self.tags = {}
        seed = [
            ("cat_ears", TagCategoryEnum.general, 30),
            ("cat_tail", TagCategoryEnum.general, 30),
            ("catxears", TagCategoryEnum.general, 5),
            ("blomblo", TagCategoryEnum.artist, 10),
            ("original", TagCategoryEnum.copyright, 20),
            ("highres", TagCategoryEnum.meta, 40),
        ]
        for name, category, post_count in seed:
            tag = Tag(name=name, category=category, post_count=post_count)
            self.db.add(tag)
            self.tags[name] = tag
        self.db.commit()
        self.db.add(TagAlias(alias_name="nekomimi", target_tag_id=self.tags["cat_ears"].id))
        self.db.add(TagAlias(alias_name="catears", target_tag_id=self.tags["cat_ears"].id))
        self.db.commit()

    def _list(self, **overrides):
        params = dict(
            request=None, page=1, limit=50, sort="post_count", order="desc",
            q=None, categories=None, db=self.db
        )
        params.update(overrides)
        return asyncio.run(get_tags_list(**params))

    def _names(self, result):
        return [item.name if hasattr(item, "name") else item["name"] for item in result["items"]]

    def test_default_sort_and_payload(self):
        result = self._list()
        self.assertEqual(result["total"], 6)
        self.assertEqual(self._names(result)[0], "highres")
        item = next(i for i in result["items"] if i.name == "cat_ears")
        self.assertEqual(item.aliases, ["catears", "nekomimi"])
        self.assertEqual(item.category, TagCategoryEnum.general)

    def test_search_matches_underscore_literally(self):
        result = self._list(q="cat_ears")
        self.assertEqual(self._names(result), ["cat_ears"])

    def test_search_matches_alias(self):
        result = self._list(q="nekomimi")
        self.assertEqual(self._names(result), ["cat_ears"])

    def test_search_percent_is_literal(self):
        self.assertEqual(self._list(q="%")["total"], 0)

    def test_category_filter(self):
        result = self._list(categories="artist,meta")
        self.assertEqual(sorted(self._names(result)), ["blomblo", "highres"])

    def test_invalid_categories_return_nothing(self):
        self.assertEqual(self._list(categories="none")["total"], 0)
        self.assertEqual(self._list(categories="bogus,nope")["total"], 0)

    def test_invalid_category_mixed_with_valid_is_ignored(self):
        result = self._list(categories="artist,bogus")
        self.assertEqual(self._names(result), ["blomblo"])

    def test_blank_categories_means_no_filter(self):
        self.assertEqual(self._list(categories="  ")["total"], 6)

    def test_sort_by_id_ascending(self):
        result = self._list(sort="id", order="asc")
        ids = [i.id for i in result["items"]]
        self.assertEqual(ids, sorted(ids))

    def test_unknown_sort_falls_back_to_post_count(self):
        result = self._list(sort="uploaded_at")
        self.assertEqual(self._names(result)[0], "highres")

    def test_pagination_is_stable_with_ties(self):
        first = self._list(limit=1, page=1)
        second = self._list(limit=1, page=2)
        self.assertEqual(first["pages"], 6)
        self.assertNotEqual(self._names(first), self._names(second))
        both = [self.tags["cat_ears"].id, self.tags["cat_tail"].id]
        tied = self._list(q="cat_", sort="post_count", order="desc")
        self.assertEqual([i.id for i in tied["items"]], sorted(both, reverse=True))

    def test_page_below_one_is_clamped(self):
        result = self._list(page=-3)
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["total"], 6)

    def test_include_aliases_false_returns_minimal_items(self):
        result = self._list(include_aliases=False)
        self.assertEqual(result["total"], 6)
        self.assertEqual(len(result["items"]), 6)
        item = result["items"][0]
        self.assertIn("id", item)
        self.assertIn("name", item)
        self.assertIn("category", item)
        self.assertNotIn("aliases", item)

    def test_high_limit_is_respected_without_aliases(self):
        result = self._list(limit=100000, include_aliases=False)
        self.assertEqual(result["limit"], 100000)
        self.assertEqual(result["total"], 6)
        self.assertEqual(len(result["items"]), 6)

    def test_high_limit_with_aliases_is_capped(self):
        result = self._list(limit=100000, include_aliases=True)
        self.assertEqual(result["limit"], 200)

    def test_slash_tag_route_matching(self):
        from backend.app.routes.tags import get_tag, router
        slash_tag = Tag(name="fate/grand_order", category=TagCategoryEnum.copyright, post_count=10)
        self.db.add(slash_tag)
        self.db.commit()

        # Direct function call
        res = asyncio.run(get_tag(request=None, tag_name="fate/grand_order", db=self.db))
        self.assertEqual(res.name, "fate/grand_order")

        # Starlette route dispatch with slashes
        scope_tag = {"type": "http", "method": "GET", "path": "/api/tags/fate/grand_order"}
        matching_tag = [r for r in router.routes if r.matches(scope_tag)[0].value == 2]
        self.assertEqual(len(matching_tag), 1)
        self.assertEqual(matching_tag[0].name, "get_tag")
        self.assertEqual(matching_tag[0].matches(scope_tag)[1]["path_params"], {"tag_name": "fate/grand_order"})

        scope_related = {"type": "http", "method": "GET", "path": "/api/tags/fate/grand_order/related"}
        matching_rel = [r for r in router.routes if r.matches(scope_related)[0].value == 2]
        self.assertEqual(len(matching_rel), 2)  # get_related_tags and fallback get_tag
        self.assertEqual(matching_rel[0].name, "get_related_tags")
        self.assertEqual(matching_rel[0].matches(scope_related)[1]["path_params"], {"tag_name": "fate/grand_order"})

    def test_bulk_update_tag_category(self):
        from backend.app.routes.admin.tags import BulkCategoryUpdateRequest, bulk_update_tag_category
        admin_user = User(id=99, username="admin_tester", password_hash="hash")
        self.db.add(admin_user)
        self.db.commit()

        tag_ids = [self.tags["cat_ears"].id, self.tags["cat_tail"].id]
        req = BulkCategoryUpdateRequest(tag_ids=tag_ids, category=TagCategoryEnum.character)
        res = asyncio.run(bulk_update_tag_category(data=req, current_user=admin_user, db=self.db))
        self.assertEqual(res["updated"], 2)

        self.db.refresh(self.tags["cat_ears"])
        self.db.refresh(self.tags["cat_tail"])
        self.assertEqual(self.tags["cat_ears"].category, TagCategoryEnum.character)
        self.assertEqual(self.tags["cat_tail"].category, TagCategoryEnum.character)

    def test_filter_by_rating(self):
        from backend.app.enums import RatingEnum
        from backend.app.routes.tags import get_tags

        # Give cat_ears safe rating and cat_tail explicit rating
        self.tags["cat_ears"].rating = RatingEnum.safe
        self.tags["cat_tail"].rating = RatingEnum.explicit
        self.db.commit()

        # Unrated tags are always included in results
        # Query safe tags -> cat_ears + unrated tags (neko, cat, feline, tail)
        safe_list = self._list(rating="safe")
        self.assertIn("cat_ears", self._names(safe_list))
        self.assertNotIn("cat_tail", self._names(safe_list))
        self.assertEqual(safe_list["total"], 5)

        # Query explicit tags -> cat_tail + unrated tags
        expl_list = self._list(rating="explicit")
        self.assertIn("cat_tail", self._names(expl_list))
        self.assertNotIn("cat_ears", self._names(expl_list))
        self.assertEqual(expl_list["total"], 5)

        # Query both safe and explicit tags
        safe_expl = self._list(rating="safe,explicit")
        self.assertIn("cat_ears", self._names(safe_expl))
        self.assertIn("cat_tail", self._names(safe_expl))
        self.assertEqual(safe_expl["total"], 6)

        # When all ratings are selected, no filtering is applied
        all_ratings = self._list(rating="safe,questionable,explicit")
        self.assertEqual(all_ratings["total"], 6)

        # Also test get_tags route function
        res_tags = asyncio.run(get_tags(request=None, rating="safe", db=self.db))
        names = [t.name for t in res_tags]
        self.assertIn("cat_ears", names)
        self.assertNotIn("cat_tail", names)

    def test_create_and_update_tag_rating(self):
        from backend.app.enums import RatingEnum
        from backend.app.routes.tags import create_tag, update_tag
        from backend.app.routes.admin.tags import update_tag as admin_update_tag, bulk_update_tag_rating, merge_tag, MergeTagRequest
        from backend.app.schemas import BulkRatingUpdateRequest, TagCreate

        admin_user = User(id=99, username="admin_tester", password_hash="hash")
        self.db.add(admin_user)
        self.db.commit()

        # Create tag without rating
        new_tag_1 = asyncio.run(create_tag(
            tag_data=TagCreate(name="rating_test_none", category=TagCategoryEnum.general),
            current_user=admin_user,
            db=self.db
        ))
        self.assertEqual(new_tag_1.rating, "none")

        # Create tag with explicit rating
        new_tag_2 = asyncio.run(create_tag(
            tag_data=TagCreate(name="rating_test_safe", category=TagCategoryEnum.general, rating="safe"),
            current_user=admin_user,
            db=self.db
        ))
        self.assertEqual(new_tag_2.rating, "safe")

        # Update tag rating via tags.py patch endpoint
        res = asyncio.run(update_tag(
            tag_id=new_tag_2.id,
            category=TagCategoryEnum.general,
            rating="questionable",
            current_user=admin_user,
            db=self.db
        ))
        self.assertEqual(res["message"], "Tag updated successfully")
        self.db.refresh(self.db.query(Tag).filter(Tag.id == new_tag_2.id).first())
        tag_obj = self.db.query(Tag).filter(Tag.id == new_tag_2.id).first()
        self.assertEqual(tag_obj.rating, RatingEnum.questionable)

        # Admin update tag without rating field in data dict (should not error and retain rating)
        admin_res = asyncio.run(admin_update_tag(
            tag_id=new_tag_2.id,
            data={"name": "rating_test_safe_renamed", "category": "general"},
            current_user=admin_user,
            db=self.db
        ))
        self.assertEqual(admin_res["tag_name"], "rating_test_safe_renamed")
        self.assertEqual(admin_res["rating"], "questionable")

        # Admin update tag setting rating to none
        admin_res_none = asyncio.run(admin_update_tag(
            tag_id=new_tag_2.id,
            data={"name": "rating_test_safe_renamed", "category": "general", "rating": "none"},
            current_user=admin_user,
            db=self.db
        ))
        self.assertEqual(admin_res_none["rating"], "none")

        # Test bulk rating update
        bulk_res = asyncio.run(bulk_update_tag_rating(
            data=BulkRatingUpdateRequest(tag_ids=[new_tag_1.id, new_tag_2.id], rating="explicit"),
            current_user=admin_user,
            db=self.db
        ))
        self.assertEqual(bulk_res["updated"], 2)
        self.db.refresh(tag_obj)
        self.assertEqual(tag_obj.rating, RatingEnum.explicit)

        # Test merge_tag rating inheritance:
        # source has explicit rating, target is unrated -> target inherits rating
        source_tag = asyncio.run(create_tag(
            tag_data=TagCreate(name="merge_src_explicit", category=TagCategoryEnum.general, rating="explicit"),
            current_user=admin_user,
            db=self.db
        ))
        target_tag = asyncio.run(create_tag(
            tag_data=TagCreate(name="merge_target_unrated", category=TagCategoryEnum.general),
            current_user=admin_user,
            db=self.db
        ))
        target_db_tag = self.db.query(Tag).filter(Tag.id == target_tag.id).first()
        self.assertIsNone(target_db_tag.rating)
        asyncio.run(merge_tag(
            tag_id=source_tag.id,
            request_data=MergeTagRequest(target_tag_name="merge_target_unrated"),
            db=self.db,
            current_user=admin_user
        ))
        merged_target = self.db.query(Tag).filter(Tag.name == "merge_target_unrated").first()
        self.assertEqual(merged_target.rating, RatingEnum.explicit)

        # source has explicit rating, target has safe rating -> target keeps safe rating
        source_tag2 = asyncio.run(create_tag(
            tag_data=TagCreate(name="merge_src_explicit2", category=TagCategoryEnum.general, rating="explicit"),
            current_user=admin_user,
            db=self.db
        ))
        target_tag2 = asyncio.run(create_tag(
            tag_data=TagCreate(name="merge_target_safe", category=TagCategoryEnum.general, rating="safe"),
            current_user=admin_user,
            db=self.db
        ))
        asyncio.run(merge_tag(
            tag_id=source_tag2.id,
            request_data=MergeTagRequest(target_tag_name="merge_target_safe"),
            db=self.db,
            current_user=admin_user
        ))
        merged_target2 = self.db.query(Tag).filter(Tag.name == "merge_target_safe").first()
        self.assertEqual(merged_target2.rating, RatingEnum.safe)

        # Test partial update_tag with only rating (name omitted)
        from backend.app.routes.admin.tags import update_tag as admin_update_tag
        res = asyncio.run(admin_update_tag(
            tag_id=merged_target2.id,
            data={"rating": "questionable"},
            current_user=admin_user,
            db=self.db
        ))
        self.assertEqual(res["rating"], "questionable")
        self.db.refresh(merged_target2)
        self.assertEqual(merged_target2.rating, RatingEnum.questionable)

        # Test rating=none filter behavior: returns ONLY unrated tags
        none_res = self._list(rating="none")
        none_tags = none_res["items"]
        self.assertTrue(len(none_tags) > 0)
        self.assertTrue(all((t.rating if hasattr(t, "rating") else t.get("rating")) == "none" for t in none_tags))

        # Test backup import updating existing tag rating
        from backend.app.utils.backup import import_tags_logical
        import_tags_logical(self.db, [{"name": "merge_target_safe", "rating": "explicit"}], [])
        self.db.refresh(merged_target2)
        self.assertEqual(merged_target2.rating, RatingEnum.explicit)

        # Test enrich_and_resolve_tags populates rating on BooruTag
        from backend.app.utils.tag_utils import enrich_and_resolve_tags
        enriched = enrich_and_resolve_tags(self.db, [{"name": "merge_target_safe", "category": "general"}], dry_run=True)
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0].rating, "explicit")

        # Test _fetch_media_batch_tags_only includes rating in tags
        from backend.app.routes.media import _fetch_media_batch_tags_only
        from backend.app.models import Media
        media_item = Media(filename="test_rating.jpg", path="test_rating.jpg", hash="testratinghash123", file_type="image", rating=RatingEnum.safe)
        media_item.tags.append(merged_target2)
        self.db.add(media_item)
        self.db.commit()
        batch_light = _fetch_media_batch_tags_only(self.db, [media_item.id])
        self.assertEqual(len(batch_light), 1)
        self.assertEqual(batch_light[0]["tags"][0]["rating"], "explicit")

    def test_escalated_rating_helper(self):
        from backend.app.enums import RatingEnum
        from backend.app.utils.tag_utils import get_escalated_rating
        from backend.app.models import Tag

        # Safe escalates to questionable or explicit
        self.assertEqual(
            get_escalated_rating(RatingEnum.safe, [Tag(rating=RatingEnum.questionable)]),
            RatingEnum.questionable
        )
        self.assertEqual(
            get_escalated_rating(RatingEnum.safe, [Tag(rating=RatingEnum.explicit)]),
            RatingEnum.explicit
        )
        # Questionable escalates to explicit
        self.assertEqual(
            get_escalated_rating(RatingEnum.questionable, [Tag(rating=RatingEnum.explicit)]),
            RatingEnum.explicit
        )
        # Escalations only: questionable never moves down to safe
        self.assertEqual(
            get_escalated_rating(RatingEnum.questionable, [Tag(rating=RatingEnum.safe)]),
            RatingEnum.questionable
        )
        # Escalations only: explicit never moves down to safe or questionable
        self.assertEqual(
            get_escalated_rating(RatingEnum.explicit, [Tag(rating=RatingEnum.safe)]),
            RatingEnum.explicit
        )
        self.assertEqual(
            get_escalated_rating(RatingEnum.explicit, [Tag(rating=RatingEnum.questionable)]),
            RatingEnum.explicit
        )
        # Handles dicts and unrated (none)
        self.assertEqual(
            get_escalated_rating(RatingEnum.safe, [{"rating": "questionable"}]),
            RatingEnum.questionable
        )
        self.assertEqual(
            get_escalated_rating(RatingEnum.safe, [{"rating": "none"}, {"rating": None}]),
            RatingEnum.safe
        )

    def test_media_rating_escalation_on_update(self):
        from backend.app.enums import RatingEnum
        from backend.app.models import Media, Tag
        from backend.app.routes.media import update_media
        from backend.app.schemas import MediaUpdate

        admin_user = User(id=999, username="admin_updater", password_hash="hash")
        self.db.add(admin_user)

        # Ensure cat_ears is safe, cat_tail is explicit
        self.tags["cat_ears"].rating = RatingEnum.safe
        self.tags["cat_tail"].rating = RatingEnum.explicit

        media = Media(
            filename="escalate_test.jpg",
            path="escalate_test.jpg",
            hash="escalatetest123",
            file_type="image",
            file_size=100,
            rating=RatingEnum.safe
        )
        self.db.add(media)
        self.db.commit()

        # Update media by adding explicit tag -> rating escalates from safe to explicit
        req = MediaUpdate(tags=["cat_tail"])
        updated = asyncio.run(update_media(media_id=media.id, updates=req, current_user=admin_user, db=self.db))
        self.assertEqual(updated.rating, "explicit")
        self.db.refresh(media)
        self.assertEqual(media.rating, RatingEnum.explicit)

        # Update media by adding safe tag -> rating stays explicit (no downgrade to safe!)
        req2 = MediaUpdate(tags=["cat_ears"])
        updated2 = asyncio.run(update_media(media_id=media.id, updates=req2, current_user=admin_user, db=self.db))
        self.assertEqual(updated2.rating, "explicit")
        self.db.refresh(media)
        self.assertEqual(media.rating, RatingEnum.explicit)

    def test_media_rating_escalation_bulk_update_tags(self):
        from backend.app.enums import RatingEnum
        from backend.app.models import Media
        from backend.app.routes.media import bulk_update_tags
        from backend.app.schemas import BulkTagUpdateRequest, BulkTagUpdateItem

        admin_user = self.db.query(User).filter(User.username == "admin_updater").first()
        if not admin_user:
            admin_user = User(id=998, username="admin_updater", password_hash="hash")
            self.db.add(admin_user)

        self.tags["cat_tail"].rating = RatingEnum.explicit
        media = Media(
            filename="bulk_escalate.jpg",
            path="bulk_escalate.jpg",
            hash="bulkescalate123",
            file_type="image",
            file_size=100,
            rating=RatingEnum.safe
        )
        self.db.add(media)
        self.db.commit()

        req = BulkTagUpdateRequest(items=[BulkTagUpdateItem(id=media.id, tags=["cat_tail"])])
        res = asyncio.run(bulk_update_tags(payload=req, current_user=admin_user, db=self.db))
        self.assertEqual(res.status, "success")
        self.db.refresh(media)
        self.assertEqual(media.rating, RatingEnum.explicit)

    def test_tag_autocomplete_rating_filter(self):
        from starlette.requests import Request
        from backend.app.enums import RatingEnum
        from backend.app.routes.tags import autocomplete_tags

        # Set ratings: cat_ears=safe, cat_tail=explicit, catxears=None (unrated)
        self.tags["cat_ears"].rating = RatingEnum.safe
        self.tags["cat_tail"].rating = RatingEnum.explicit
        self.tags["catxears"].rating = None
        self.db.commit()

        mock_req = Request({"type": "http", "method": "GET", "url": "http://testserver/api/tags/autocomplete", "headers": []})

        # Autocomplete with rating=safe: includes cat_ears and catxears (unrated), excludes cat_tail (explicit)
        res_safe = asyncio.run(autocomplete_tags(request=mock_req, q="cat", rating="safe", db=self.db))
        names_safe = {r["name"] for r in res_safe}
        self.assertIn("cat_ears", names_safe)
        self.assertIn("catxears", names_safe)
        self.assertNotIn("cat_tail", names_safe)

        # Autocomplete with rating=explicit: includes cat_tail and catxears (unrated), excludes cat_ears (safe)
        res_expl = asyncio.run(autocomplete_tags(request=mock_req, q="cat", rating="explicit", db=self.db))
        names_expl = {r["name"] for r in res_expl}
        self.assertIn("cat_tail", names_expl)
        self.assertIn("catxears", names_expl)
        self.assertNotIn("cat_ears", names_expl)

        # Autocomplete with all ratings: includes all
        res_all = asyncio.run(autocomplete_tags(request=mock_req, q="cat", rating="safe,questionable,explicit", db=self.db))
        names_all = {r["name"] for r in res_all}
        self.assertIn("cat_ears", names_all)
        self.assertIn("cat_tail", names_all)
        self.assertIn("catxears", names_all)

        # Autocomplete with rating=none: only unrated tags
        res_none = asyncio.run(autocomplete_tags(request=mock_req, q="cat", rating="none", db=self.db))
        names_none = {r["name"] for r in res_none}
        self.assertIn("catxears", names_none)
        self.assertNotIn("cat_ears", names_none)
        self.assertNotIn("cat_tail", names_none)

    def test_autocomplete_tags_wildcard_patterns(self):
        from starlette.requests import Request
        from backend.app.routes.tags import autocomplete_tags

        mock_req = Request({"type": "http", "method": "GET", "url": "http://testserver/api/tags/autocomplete", "headers": []})

        # Wildcard prefix matching "cat*"
        res = asyncio.run(autocomplete_tags(request=mock_req, q="cat*", db=self.db))
        names = [r["name"] for r in res]
        self.assertIn("cat_ears", names)
        self.assertIn("cat_tail", names)
        self.assertIn("catxears", names)
        self.assertNotIn("original", names)

        # Single character wildcard "?at_ears"
        res_single = asyncio.run(autocomplete_tags(request=mock_req, q="?at_ears", db=self.db))
        names_single = [r["name"] for r in res_single]
        self.assertIn("cat_ears", names_single)
        self.assertNotIn("cat_tail", names_single)

        # Empty wildcard query should return empty list
        res_empty = asyncio.run(autocomplete_tags(request=mock_req, q="***", db=self.db))
        self.assertEqual(res_empty, [])

    def test_tags_list_unfiltered_total_on_filter_hidden(self):
        from backend.app.enums import RatingEnum
        self.tags["cat_ears"].rating = RatingEnum.explicit
        self.db.commit()

        # Query "cat_ears" with rating="safe" -> filtered out by rating
        res = self._list(q="cat_ears", rating="safe")
        self.assertEqual(res["total"], 0)
        self.assertEqual(res["unfiltered_total"], 1)

        # Query nonexistent tag with rating="safe" -> no results regardless of filter
        res_none = self._list(q="nonexistent_xyz", rating="safe")
        self.assertEqual(res_none["total"], 0)
        self.assertEqual(res_none["unfiltered_total"], 0)

        # Query "cat_ears" with categories="artist" -> filtered out by category
        res_cat = self._list(q="cat_ears", categories="artist")
        self.assertEqual(res_cat["total"], 0)
        self.assertEqual(res_cat["unfiltered_total"], 1)
