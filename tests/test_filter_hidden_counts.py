import asyncio
import unittest

from backend.app.enums import FileTypeEnum, RatingEnum, TagCategoryEnum
from backend.app.models import Album, Media, Tag, blombooru_album_media
from backend.app.routes.albums import get_album_contents, get_albums
from backend.app.routes.media import get_media_list
from backend.app.routes.search import search_media
from backend.app.routes.tags import get_tags_list
from tests.test_base import BackupTestBase

class DummyRequest:
    def __init__(self):
        self.headers = {}
        self.query_params = {}

class TestFilterHiddenCounts(BackupTestBase):
    def setUp(self):
        super().setUp()

    def test_media_list_and_search_hidden_counts(self):
        # 1. Empty database: unfiltered_total must be 0
        res_empty = asyncio.run(get_media_list(DummyRequest(), page=1, limit=20, rating="safe", db=self.db))
        self.assertEqual(res_empty["total"], 0)
        self.assertEqual(res_empty["unfiltered_total"], 0)

        search_empty = asyncio.run(search_media(DummyRequest(), q="cat", rating="safe", db=self.db))
        self.assertEqual(search_empty["total"], 0)
        self.assertEqual(search_empty["unfiltered_total"], 0)

        # 2. Add an explicit media with tag "cat"
        tag_cat = Tag(name="cat", category=TagCategoryEnum.general, rating=RatingEnum.explicit)
        self.db.add(tag_cat)
        media_explicit = Media(
            filename="cat.jpg",
            path="cat.jpg",
            thumbnail_path="cat_thumb.jpg",
            hash="hash_cat",
            file_size=1000,
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            rating=RatingEnum.explicit
        )
        media_explicit.tags.append(tag_cat)
        self.db.add(media_explicit)
        self.db.commit()

        # get_media_list with rating="safe": filtered out by sidebar rating
        res_filtered = asyncio.run(get_media_list(DummyRequest(), page=1, limit=20, rating="safe", db=self.db))
        self.assertEqual(res_filtered["total"], 0)
        self.assertEqual(res_filtered["unfiltered_total"], 1)

        # search_media with q="cat" and rating="safe": filtered out by sidebar rating
        search_filtered = asyncio.run(search_media(DummyRequest(), q="cat", rating="safe", db=self.db))
        self.assertEqual(search_filtered["total"], 0)
        self.assertEqual(search_filtered["unfiltered_total"], 1)

        # search_media with query matching nothing regardless of rating filter
        search_nonexistent = asyncio.run(search_media(DummyRequest(), q="dog", rating="safe", db=self.db))
        self.assertEqual(search_nonexistent["total"], 0)
        self.assertEqual(search_nonexistent["unfiltered_total"], 0)

        # search_media where rating filter is specified inside search bar
        search_in_q = asyncio.run(search_media(DummyRequest(), q="cat rating:safe", db=self.db))
        self.assertEqual(search_in_q["total"], 0)
        self.assertEqual(search_in_q["unfiltered_total"], 0)

    def test_albums_and_album_contents_hidden_counts(self):
        # Create an album containing the explicit media
        album = Album(name="My Album", cached_media_count=1)
        self.db.add(album)
        self.db.commit()

        media = Media(
            filename="art.jpg",
            path="art.jpg",
            thumbnail_path="art_thumb.jpg",
            hash="hash_art",
            file_size=2000,
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            rating=RatingEnum.explicit
        )
        self.db.add(media)
        self.db.commit()

        self.db.execute(
            blombooru_album_media.insert().values(
                album_id=album.id,
                media_id=media.id,
                sort_position=1
            )
        )
        self.db.commit()

        # get_albums with root_only=True, rating="safe"
        albums_res = asyncio.run(get_albums(DummyRequest(), root_only=True, rating="safe", db=self.db))
        self.assertEqual(albums_res["total"], 0)
        self.assertEqual(albums_res["unfiltered_total"], 1)

        # get_albums with q matching nothing
        albums_nonexistent = asyncio.run(get_albums(DummyRequest(), root_only=True, q="nonexistent", rating="safe", db=self.db))
        self.assertEqual(albums_nonexistent["total"], 0)
        self.assertEqual(albums_nonexistent["unfiltered_total"], 0)

        # get_album_contents with rating="safe"
        contents = asyncio.run(get_album_contents(DummyRequest(), album.id, rating="safe", db=self.db))
        self.assertEqual(contents["total_media"], 0)
        self.assertEqual(contents["unfiltered_total_media"], 1)

    def test_tags_list_hidden_counts(self):
        tag = Tag(name="dragon", category=TagCategoryEnum.general, rating=RatingEnum.explicit, post_count=5)
        self.db.add(tag)
        self.db.commit()

        # Filtered by sidebar rating
        res_rating = asyncio.run(get_tags_list(DummyRequest(), q="dragon", rating="safe", db=self.db))
        self.assertEqual(res_rating["total"], 0)
        self.assertEqual(res_rating["unfiltered_total"], 1)

        # Filtered by sidebar categories
        res_cat = asyncio.run(get_tags_list(DummyRequest(), q="dragon", categories="artist", db=self.db))
        self.assertEqual(res_cat["total"], 0)
        self.assertEqual(res_cat["unfiltered_total"], 1)

        # Nonexistent tag regardless of filters
        res_none = asyncio.run(get_tags_list(DummyRequest(), q="unicorn", rating="safe", db=self.db))
        self.assertEqual(res_none["total"], 0)
        self.assertEqual(res_none["unfiltered_total"], 0)

if __name__ == "__main__":
    unittest.main()
