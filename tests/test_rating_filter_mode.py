import asyncio
import urllib.parse
from fastapi import Request

from backend.app.config import settings
from backend.app.enums import FileTypeEnum, RatingEnum, TagCategoryEnum
from backend.app.models import Album, Media, Tag, blombooru_album_media, blombooru_media_tags
from backend.app.redis_client import redis_cache
from backend.app.routes.albums import get_album_contents, get_albums
from backend.app.routes.media import (get_adjacent_media, get_media_list,
                                      get_related_media)
from backend.app.routes.search import get_random_media, search_media
from backend.app.routes.tags import search_related_tags
from backend.app.utils.album_utils import recalculate_all_album_metrics
from backend.app.schemas import SettingsUpdate
from tests.backup_test_base import BackupTestBase

def make_dummy_request(path: str = "/api/test", query_params: dict = None) -> Request:
    query_str = urllib.parse.urlencode(query_params or {}).encode()
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": query_str,
    }
    return Request(scope)

class TestRatingFilterMode(BackupTestBase):
    def setUp(self):
        super().setUp()
        self.old_redis_enabled = redis_cache._enabled
        redis_cache._enabled = False

        # Seed test media items with safe, questionable, and explicit ratings
        self.media_safe = Media(
            id=1,
            filename="safe_1.jpg",
            path="original/safe_1.jpg",
            hash="hash_safe_1",
            file_type=FileTypeEnum.image,
            rating=RatingEnum.safe,
            file_size=1024,
        )
        self.media_quest = Media(
            id=2,
            filename="quest_1.jpg",
            path="original/quest_1.jpg",
            hash="hash_quest_1",
            file_type=FileTypeEnum.image,
            rating=RatingEnum.questionable,
            file_size=2048,
        )
        self.media_expl = Media(
            id=3,
            filename="expl_1.jpg",
            path="original/expl_1.jpg",
            hash="hash_expl_1",
            file_type=FileTypeEnum.image,
            rating=RatingEnum.explicit,
            file_size=4096,
        )
        self.db.add_all([self.media_safe, self.media_quest, self.media_expl])

        self.tag_cat = Tag(id=1, name="cat", category=TagCategoryEnum.character, post_count=3)
        self.db.add(self.tag_cat)
        self.db.commit()

        # Link tag to all media
        self.db.execute(blombooru_media_tags.insert().values([
            {"media_id": 1, "tag_id": 1},
            {"media_id": 2, "tag_id": 1},
            {"media_id": 3, "tag_id": 1},
        ]))
        self.db.commit()

    def tearDown(self):
        redis_cache._enabled = self.old_redis_enabled
        super().tearDown()

    def test_search_media_ratings(self):
        req = make_dummy_request()

        def get_ids(res):
            return [item["id"] if isinstance(item, dict) else item.id for item in res["items"]]

        # 1. Default (omitted rating) -> returns all media
        res_all = asyncio.run(search_media(request=req, db=self.db))
        self.assertCountEqual(get_ids(res_all), [1, 2, 3])

        # 2. Single ratings
        res_safe = asyncio.run(search_media(request=req, rating="safe", db=self.db))
        self.assertEqual(get_ids(res_safe), [1])

        res_quest = asyncio.run(search_media(request=req, rating="questionable", db=self.db))
        self.assertEqual(get_ids(res_quest), [2])

        res_expl = asyncio.run(search_media(request=req, rating="explicit", db=self.db))
        self.assertEqual(get_ids(res_expl), [3])

        # 3. Multi-ratings
        res_safe_quest = asyncio.run(search_media(request=req, rating="safe,questionable", db=self.db))
        self.assertCountEqual(get_ids(res_safe_quest), [1, 2])

        res_safe_expl = asyncio.run(search_media(request=req, rating="safe,explicit", db=self.db))
        self.assertCountEqual(get_ids(res_safe_expl), [1, 3])

        res_quest_expl = asyncio.run(search_media(request=req, rating="questionable,explicit", db=self.db))
        self.assertCountEqual(get_ids(res_quest_expl), [2, 3])

        res_all_ratings = asyncio.run(search_media(request=req, rating="safe,questionable,explicit", db=self.db))
        self.assertCountEqual(get_ids(res_all_ratings), [1, 2, 3])

    def test_get_media_list_ratings(self):
        req = make_dummy_request()

        def get_ids(res):
            return [item["id"] if isinstance(item, dict) else item.id for item in res["items"]]

        # 1. Default (omitted rating) -> returns all media
        res_all = asyncio.run(get_media_list(request=req, db=self.db))
        self.assertCountEqual(get_ids(res_all), [1, 2, 3])

        # 2. Single ratings
        res_safe = asyncio.run(get_media_list(request=req, rating="safe", db=self.db))
        self.assertEqual(get_ids(res_safe), [1])

        res_quest = asyncio.run(get_media_list(request=req, rating="questionable", db=self.db))
        self.assertEqual(get_ids(res_quest), [2])

        res_expl = asyncio.run(get_media_list(request=req, rating="explicit", db=self.db))
        self.assertEqual(get_ids(res_expl), [3])

        # 3. Multi-ratings
        res_safe_quest = asyncio.run(get_media_list(request=req, rating="safe,questionable", db=self.db))
        self.assertCountEqual(get_ids(res_safe_quest), [1, 2])

        res_safe_expl = asyncio.run(get_media_list(request=req, rating="safe,explicit", db=self.db))
        self.assertCountEqual(get_ids(res_safe_expl), [1, 3])

    def test_get_random_media_ratings(self):
        res_expl = asyncio.run(get_random_media(rating="explicit", db=self.db))
        self.assertEqual(res_expl["id"], 3)

        res_quest = asyncio.run(get_random_media(rating="questionable", db=self.db))
        self.assertEqual(res_quest["id"], 2)

        res_safe = asyncio.run(get_random_media(rating="safe", db=self.db))
        self.assertEqual(res_safe["id"], 1)

        res_multi = asyncio.run(get_random_media(rating="safe,questionable", db=self.db))
        self.assertIn(res_multi["id"], [1, 2])

    def test_get_adjacent_media_ratings(self):
        # In questionable only mode, adjacent media for id=2 should have no prev or next among safe/explicit
        res = asyncio.run(get_adjacent_media(media_id=2, rating="questionable", db=self.db))
        self.assertIsNone(res.get("prev_id"))
        self.assertIsNone(res.get("next_id"))

        # In all ratings mode with order=asc, next for id=1 should be id=2
        res_all = asyncio.run(get_adjacent_media(media_id=1, rating="safe,questionable,explicit", order="asc", db=self.db))
        self.assertEqual(res_all.get("next_id"), 2)

        # In safe,explicit mode with order=asc, next for id=1 should skip questionable and be id=3
        res_skip = asyncio.run(get_adjacent_media(media_id=1, rating="safe,explicit", order="asc", db=self.db))
        self.assertEqual(res_skip.get("next_id"), 3)

    def test_albums_ratings(self):
        req = make_dummy_request()

        def get_album_names(res):
            return [a["name"] if isinstance(a, dict) else a.name for a in res["items"]]

        # Create 3 albums: one containing only safe, one questionable, one explicit
        a_safe = Album(id=1, name="Album Safe")
        a_quest = Album(id=2, name="Album Quest")
        a_expl = Album(id=3, name="Album Expl")
        self.db.add_all([a_safe, a_quest, a_expl])
        self.db.commit()

        self.db.execute(blombooru_album_media.insert().values([
            {"album_id": 1, "media_id": 1},
            {"album_id": 2, "media_id": 2},
            {"album_id": 3, "media_id": 3},
        ]))
        self.db.commit()
        recalculate_all_album_metrics(self.db)

        # 1. get_albums with multi-rating safe,questionable
        albums_quest = asyncio.run(get_albums(request=req, rating="safe,questionable", db=self.db))
        names = get_album_names(albums_quest)
        self.assertIn("Album Safe", names)
        self.assertIn("Album Quest", names)
        self.assertNotIn("Album Expl", names)

        # 2. get_albums with single rating questionable
        albums_quest_exact = asyncio.run(get_albums(request=req, rating="questionable", db=self.db))
        exact_names = get_album_names(albums_quest_exact)
        self.assertNotIn("Album Safe", exact_names)
        self.assertEqual(exact_names, ["Album Quest"])

        # 3. get_albums with safe,explicit (skipping questionable)
        albums_safe_expl = asyncio.run(get_albums(request=req, rating="safe,explicit", db=self.db))
        skip_names = get_album_names(albums_safe_expl)
        self.assertIn("Album Safe", skip_names)
        self.assertIn("Album Expl", skip_names)
        self.assertNotIn("Album Quest", skip_names)

        # 4. get_album_contents
        # In album 1 (containing media_safe), querying rating="questionable" should return 0 media
        contents_quest = asyncio.run(get_album_contents(request=req, album_id=1, rating="questionable", db=self.db))
        self.assertEqual(len(contents_quest["media"]), 0)

        # Querying rating="safe,questionable" should return media_safe (id=1)
        contents_inc = asyncio.run(get_album_contents(request=req, album_id=1, rating="safe,questionable", db=self.db))
        self.assertEqual(len(contents_inc["media"]), 1)

    def test_search_related_tags_ratings(self):
        req = make_dummy_request()

        # Add unique tag to explicit media only
        tag_expl = Tag(id=2, name="nsfw_tag", category=TagCategoryEnum.general, post_count=1)
        self.db.add(tag_expl)
        self.db.commit()
        self.db.execute(blombooru_media_tags.insert().values([
            {"media_id": 3, "tag_id": 2}
        ]))
        self.db.commit()

        # Search related tags for query="cat" with rating="safe" -> nsfw_tag should NOT be in results
        tags_safe = asyncio.run(search_related_tags(request=req, q="cat", rating="safe", db=self.db))
        tag_names_safe = [t["name"] for t in tags_safe]
        self.assertNotIn("nsfw_tag", tag_names_safe)

        # Search related tags for query="cat" with rating="explicit" -> nsfw_tag should be present
        tags_expl = asyncio.run(search_related_tags(request=req, q="cat", rating="explicit", db=self.db))
        tag_names_expl = [t["name"] for t in tags_expl]
        self.assertIn("nsfw_tag", tag_names_expl)

        # Search related tags for query="cat" with rating="safe,explicit" -> nsfw_tag should be present
        tags_multi = asyncio.run(search_related_tags(request=req, q="cat", rating="safe,explicit", db=self.db))
        tag_names_multi = [t["name"] for t in tags_multi]
        self.assertIn("nsfw_tag", tag_names_multi)

    def test_user_typed_rating_in_q_overrides_sidebar_rating(self):
        """Verify that user-typed rating in search query (q) takes precedence over top-level rating parameter."""
        req = make_dummy_request()

        def get_ids(res):
            return [item["id"] if isinstance(item, dict) else item.id for item in res["items"]]

        # Tag media 3 with tag 'dog'
        tag_dog = Tag(id=40, name="dog", category=TagCategoryEnum.general, post_count=1)
        self.db.add(tag_dog)
        self.db.commit()
        self.db.execute(blombooru_media_tags.insert().values([{"media_id": 3, "tag_id": 40}]))
        self.db.commit()

        # 1. search_media with top-level rating="safe" but query q="rating:explicit"
        # Should return media 3 (explicit) because user explicitly requested rating:explicit in search query
        res = asyncio.run(search_media(request=req, q="rating:explicit", rating="safe", db=self.db))
        self.assertEqual(get_ids(res), [3])

        # 2. search_related_tags with top-level rating="safe" but query q="cat rating:explicit"
        # Should include tags on explicit media 3
        tags_res = asyncio.run(search_related_tags(request=req, q="cat rating:explicit", rating="safe", db=self.db))
        tag_names = [t["name"] for t in tags_res]
        self.assertIn("dog", tag_names)

        # 3. get_adjacent_media with top-level rating="safe" but query q="rating:explicit"
        res_adj = asyncio.run(get_adjacent_media(media_id=3, q="rating:explicit", rating="safe", db=self.db))
        self.assertIn("prev_id", res_adj)

        # 4. get_album_contents with q="rating:explicit" and rating="safe"
        a = Album(id=50, name="Mixed Album")
        self.db.add(a)
        self.db.commit()
        self.db.execute(blombooru_album_media.insert().values([
            {"album_id": 50, "media_id": 1},
            {"album_id": 50, "media_id": 3},
        ]))
        self.db.commit()

        res_contents = asyncio.run(get_album_contents(request=req, album_id=50, q="rating:explicit", rating="safe", db=self.db))
        self.assertEqual(len(res_contents["media"]), 1)
        self.assertEqual(res_contents["media"][0].id, 3)

    def test_order_custom_fallback(self):
        """Verify that order:custom without valid comma-separated id: list falls back cleanly to default order."""
        req = make_dummy_request()

        def get_ids(res):
            return [item["id"] if isinstance(item, dict) else item.id for item in res["items"]]

        # 1. order:custom with no id: token -> query executes with default order fallback
        res1 = asyncio.run(search_media(request=req, q="order:custom", rating="safe,questionable,explicit", db=self.db))
        self.assertEqual(len(get_ids(res1)), 3)

        # 2. order:custom with single id: token (no comma) -> query executes with fallback
        res2 = asyncio.run(search_media(request=req, q="order:custom id:1", rating="safe,questionable,explicit", db=self.db))
        self.assertEqual(get_ids(res2), [1])

        # 3. order:custom with comma-separated id:3,1,2 -> applies custom order
        res3 = asyncio.run(search_media(request=req, q="order:custom id:3,1,2", rating="safe,questionable,explicit", db=self.db))
        self.assertEqual(get_ids(res3), [3, 1, 2])

    def test_get_adjacent_media_all_three_paths(self):
        """Test all 3 branches in get_adjacent_media: non-album, album without q, album with q."""
        album = Album(id=100, name="Adjacent Test Album")
        self.db.add(album)
        self.db.commit()
        self.db.execute(blombooru_album_media.insert().values([
            {"album_id": 100, "media_id": 1},
            {"album_id": 100, "media_id": 2},
            {"album_id": 100, "media_id": 3},
        ]))
        self.db.commit()

        # Path 1: Album mode without q
        # 1a: questionable only -> only media 2 matches, so prev/next are None
        res_p1_exact = asyncio.run(get_adjacent_media(media_id=2, mode="album", album_id=100, rating="questionable", db=self.db))
        self.assertIsNone(res_p1_exact.get("prev_id"))
        self.assertIsNone(res_p1_exact.get("next_id"))

        # 1b: safe,questionable,explicit with order=asc -> media 1 next is 2
        res_p1_all = asyncio.run(get_adjacent_media(media_id=1, mode="album", album_id=100, rating="safe,questionable,explicit", order="asc", db=self.db))
        self.assertEqual(res_p1_all.get("next_id"), 2)

        # Path 2: Album mode with q
        # 2a: questionable -> media 2 with q="cat"
        res_p2_exact = asyncio.run(get_adjacent_media(media_id=2, mode="album", album_id=100, q="cat", rating="questionable", db=self.db))
        self.assertIsNone(res_p2_exact.get("prev_id"))
        self.assertIsNone(res_p2_exact.get("next_id"))

        # 2b: multi-rating with order=asc and q="cat"
        res_p2_all = asyncio.run(get_adjacent_media(media_id=1, mode="album", album_id=100, q="cat", rating="safe,questionable,explicit", order="asc", db=self.db))
        self.assertEqual(res_p2_all.get("next_id"), 2)

        # Path 3: Non-album search mode
        # 3a: questionable -> media 2
        res_p3_exact = asyncio.run(get_adjacent_media(media_id=2, mode="search", q="cat", rating="questionable", db=self.db))
        self.assertIsNone(res_p3_exact.get("prev_id"))
        self.assertIsNone(res_p3_exact.get("next_id"))

        # 3b: multi-rating with order=asc
        res_p3_all = asyncio.run(get_adjacent_media(media_id=1, mode="search", q="cat", rating="safe,questionable,explicit", order="asc", db=self.db))
        self.assertEqual(res_p3_all.get("next_id"), 2)

    def test_both_mode_query_composition_and(self):
        """Test concurrent q and rating filter (AND composition)."""
        req = make_dummy_request()

        def get_ids(res):
            return [item["id"] if isinstance(item, dict) else item.id for item in res["items"]]

        # Tag media 1 and 2 with 'cute', media 3 with 'cool'
        tag_cute = Tag(id=50, name="cute", category=TagCategoryEnum.general, post_count=2)
        tag_cool = Tag(id=51, name="cool", category=TagCategoryEnum.general, post_count=1)
        self.db.add_all([tag_cute, tag_cool])
        self.db.commit()
        self.db.execute(blombooru_media_tags.insert().values([
            {"media_id": 1, "tag_id": 50},
            {"media_id": 2, "tag_id": 50},
            {"media_id": 3, "tag_id": 51},
        ]))
        self.db.commit()

        # q="cute" AND rating="safe" -> should return media 1 only
        res_safe = asyncio.run(search_media(request=req, q="cute", rating="safe", db=self.db))
        self.assertEqual(get_ids(res_safe), [1])

        # q="cute" AND rating="safe,questionable" -> should return media 1 and 2
        res_quest = asyncio.run(search_media(request=req, q="cute", rating="safe,questionable", db=self.db))
        self.assertCountEqual(get_ids(res_quest), [1, 2])

        # q="cute" AND rating="questionable" -> should return media 2 only
        res_exact = asyncio.run(search_media(request=req, q="cute", rating="questionable", db=self.db))
        self.assertEqual(get_ids(res_exact), [2])

    def test_custom_filters_or_mode(self):
        """Test that multiple custom sidebar buttons are ORed together."""
        req = make_dummy_request()

        # Tag media 1 and 2 with 'cute', media 3 with 'cool'
        tag_cute = Tag(id=50, name="cute", category=TagCategoryEnum.general, post_count=2)
        tag_cool = Tag(id=51, name="cool", category=TagCategoryEnum.general, post_count=1)
        self.db.add_all([tag_cute, tag_cool])
        self.db.commit()
        self.db.execute(blombooru_media_tags.insert().values([
            {"media_id": 1, "tag_id": 50},
            {"media_id": 2, "tag_id": 50},
            {"media_id": 3, "tag_id": 51},
        ]))
        self.db.commit()

        def get_ids(res):
            return [item["id"] if isinstance(item, dict) else item.id for item in res["items"]]

        # Single custom button: "cute" -> media 1, 2
        res1 = asyncio.run(search_media(request=req, custom_filter=["cute"], db=self.db))
        self.assertCountEqual(get_ids(res1), [1, 2])

        # Single custom button: "cool" -> media 3
        res2 = asyncio.run(search_media(request=req, custom_filter=["cool"], db=self.db))
        self.assertEqual(get_ids(res2), [3])

        # Two custom buttons: "cute" OR "cool" -> media 1, 2, 3
        res_or = asyncio.run(search_media(request=req, custom_filter=["cute", "cool"], db=self.db))
        self.assertCountEqual(get_ids(res_or), [1, 2, 3])

        # Two custom buttons "cute" OR "cool" AND rating="safe" -> media 1
        res_or_safe = asyncio.run(search_media(request=req, custom_filter=["cute", "cool"], rating="safe", db=self.db))
        self.assertEqual(get_ids(res_or_safe), [1])

        # get_media_list with custom_filter OR
        res_list = asyncio.run(get_media_list(request=req, custom_filter=["cute", "cool"], rating="safe,questionable", db=self.db))
        self.assertCountEqual(get_ids(res_list), [1, 2])

        # get_adjacent_media with custom_filter OR
        res_adj = asyncio.run(get_adjacent_media(media_id=1, custom_filter=["cute", "cool"], sort="id", order="asc", db=self.db))
        self.assertEqual(res_adj.get("next_id"), 2)

    def test_both_mode_custom_button_embedded_rating_override(self):
        """Test that a custom button containing rating: overrides top-level rating parameter."""
        req = make_dummy_request()

        def get_ids(res):
            return [item["id"] if isinstance(item, dict) else item.id for item in res["items"]]

        # Custom button query is 'cat rating:explicit', sidebar rating is 'safe'
        res = asyncio.run(search_media(request=req, q="cat rating:explicit", rating="safe", db=self.db))
        self.assertEqual(get_ids(res), [3])

    def test_search_related_tags_both_mode_composition(self):
        """Test related tags in both mode with query and rating filter."""
        req = make_dummy_request()

        tag_x = Tag(id=60, name="rare_tag", category=TagCategoryEnum.general, post_count=1)
        self.db.add(tag_x)
        self.db.commit()
        self.db.execute(blombooru_media_tags.insert().values([{"media_id": 2, "tag_id": 60}]))
        self.db.commit()

        # Related tags for q="cat" with rating="safe" -> rare_tag is on questionable media 2, should not appear
        res_safe = asyncio.run(search_related_tags(request=req, q="cat", rating="safe", db=self.db))
        names_safe = [t["name"] for t in res_safe]
        self.assertNotIn("rare_tag", names_safe)

        # Related tags for q="cat" with rating="safe,questionable" -> rare_tag should appear
        res_quest = asyncio.run(search_related_tags(request=req, q="cat", rating="safe,questionable", db=self.db))
        names_quest = [t["name"] for t in res_quest]
        self.assertIn("rare_tag", names_quest)

    def test_get_related_media_filters(self):
        """Test that get_related_media respects rating and custom_filter parameters."""
        from backend.app.services.similarity import similarity_index

        req = make_dummy_request()

        # Build similarity index synchronously for testing
        similarity_index.rebuild(self.db)

        def get_ids(res):
            return [item["id"] if isinstance(item, dict) else item.id for item in res["items"]]

        # Media 1 is safe, Media 2 is questionable, Media 3 is explicit (all share 'cat')
        # All ratings -> related to media 1 includes media 2 and 3
        res_all = asyncio.run(get_related_media(request=req, media_id=1, rating="safe,questionable,explicit", db=self.db))
        self.assertCountEqual(get_ids(res_all), [2, 3])

        # Rating safe only -> media 2 and 3 filtered out
        res_safe = asyncio.run(get_related_media(request=req, media_id=1, rating="safe", db=self.db))
        self.assertEqual(get_ids(res_safe), [])

        # Rating safe,questionable -> includes media 2 only
        res_quest = asyncio.run(get_related_media(request=req, media_id=1, rating="safe,questionable", db=self.db))
        self.assertEqual(get_ids(res_quest), [2])

        # Custom filter: tag media 3 with 'cool'
        tag_cool = Tag(id=51, name="cool", category=TagCategoryEnum.general, post_count=1)
        self.db.add(tag_cool)
        self.db.commit()
        self.db.execute(blombooru_media_tags.insert().values([{"media_id": 3, "tag_id": 51}]))
        self.db.commit()

        # Custom filter 'cool' -> only media 3 matches
        res_custom = asyncio.run(get_related_media(request=req, media_id=1, custom_filter=["cool"], db=self.db))
        self.assertEqual(get_ids(res_custom), [3])

    def test_config_and_schema(self):
        from pydantic import ValidationError

        # Verify SettingsUpdate schema parses valid sidebar_filter_mode values
        for mode in ["rating", "custom", "both", "off"]:
            su = SettingsUpdate(sidebar_filter_mode=mode)
            self.assertEqual(su.sidebar_filter_mode, mode)

        # Verify SettingsUpdate schema rejects invalid values
        with self.assertRaises(ValidationError):
            SettingsUpdate(sidebar_filter_mode="invalid_mode")

        # Verify config defaults and property
        self.assertEqual(settings.SIDEBAR_FILTER_MODE, "rating")

        # Verify both mode in config
        settings.save_settings({"sidebar_filter_mode": "both"})
        self.assertEqual(settings.SIDEBAR_FILTER_MODE, "both")

        # Verify corrupt/invalid value in file_settings safely falls back
        settings.file_settings["sidebar_filter_mode"] = "corrupted_mode"
        self.assertEqual(settings.SIDEBAR_FILTER_MODE, "rating")

        # Restore default
        settings.save_settings({"sidebar_filter_mode": "rating"})
        self.assertEqual(settings.SIDEBAR_FILTER_MODE, "rating")
