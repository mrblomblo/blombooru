import unittest

from backend.app.enums import FileTypeEnum, RatingEnum, TagCategoryEnum
from backend.app.models import Media, Tag
from backend.app.services.similarity import SimilarityIndex
from tests.test_base import BackupTestBase

class TestSimilarityIndex(BackupTestBase):
    def setUp(self):
        super().setUp()
        self.index = SimilarityIndex()

    def _create_media(self, media_id: int, filename: str) -> Media:
        media = Media(
            id=media_id,
            filename=filename,
            path=f"original/{filename}",
            hash=f"hash_{media_id}",
            file_type=FileTypeEnum.image,
            rating=RatingEnum.safe,
            file_size=1024,
        )
        self.db.add(media)
        return media

    def _create_tag(self, tag_id: int, name: str, category: TagCategoryEnum, post_count: int = 1) -> Tag:
        tag = Tag(id=tag_id, name=name, category=category, post_count=post_count)
        self.db.add(tag)
        return tag

    def test_media_similarity_category_weights(self):
        """
        Verify that artist and character tags heavily influence similarity ranking
        over general and meta tags.
        """
        # Create Tags
        t_artist1 = self._create_tag(1, "artist_a", TagCategoryEnum.artist, 2)
        t_char1 = self._create_tag(2, "char_a", TagCategoryEnum.character, 3)
        t_general1 = self._create_tag(3, "1girl", TagCategoryEnum.general, 5)
        t_meta1 = self._create_tag(4, "highres", TagCategoryEnum.meta, 5)
        t_copy1 = self._create_tag(5, "series_x", TagCategoryEnum.copyright, 2)

        # Media 1 (Query): artist_a, char_a, 1girl, highres
        # Media 2: artist_a, char_a, series_x (Matches artist + character!)
        # Media 3: char_a, 1girl (Matches character + general)
        # Media 4: 1girl, highres (Matches general + meta only)
        # Media 5: highres only (Matches meta only)
        m1 = self._create_media(1, "m1.jpg")
        m2 = self._create_media(2, "m2.jpg")
        m3 = self._create_media(3, "m3.jpg")
        m4 = self._create_media(4, "m4.jpg")
        m5 = self._create_media(5, "m5.jpg")
        self.db.commit()

        # Associate tags
        m1.tags = [t_artist1, t_char1, t_general1, t_meta1]
        m2.tags = [t_artist1, t_char1, t_copy1]
        m3.tags = [t_char1, t_general1]
        m4.tags = [t_general1, t_meta1]
        m5.tags = [t_meta1]
        self.db.commit()

        # Build index
        self.index.rebuild(self.db)
        self.assertTrue(self.index.is_ready)

        results = self.index.get_similar_media(1, limit=10)
        self.assertGreater(len(results), 0)

        result_ids = [mid for mid, _ in results]

        # m2 (shares artist + character) must be the top result
        self.assertEqual(result_ids[0], 2)

        # m3 (shares character) should rank above m4 (shares only general + meta)
        self.assertEqual(result_ids[1], 3)

        # Scores should be strictly descending
        scores = [score for _, score in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

        # Check self is not in results
        self.assertNotIn(1, result_ids)

    def test_album_scoped_similarity(self):
        """Verify that passing album_media_ids restricts results to that set."""
        t_artist = self._create_tag(1, "artist_a", TagCategoryEnum.artist, 4)
        m1 = self._create_media(1, "m1.jpg")
        m2 = self._create_media(2, "m2.jpg")
        m3 = self._create_media(3, "m3.jpg")
        m4 = self._create_media(4, "m4.jpg")
        self.db.commit()

        m1.tags = [t_artist]
        m2.tags = [t_artist]
        m3.tags = [t_artist]
        m4.tags = [t_artist]
        self.db.commit()

        self.index.rebuild(self.db)

        # Restrict to only m3 in album
        album_ids = {3}
        results = self.index.get_similar_media(1, limit=10, album_media_ids=album_ids)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], 3)

    def test_danbooru_related_tags(self):
        """Verify get_related_tags computes metrics accurately."""
        t_artist = self._create_tag(1, "artist_a", TagCategoryEnum.artist, 3)
        t_char = self._create_tag(2, "char_a", TagCategoryEnum.character, 3)
        t_gen = self._create_tag(3, "solo", TagCategoryEnum.general, 3)
        t_other = self._create_tag(4, "other_tag", TagCategoryEnum.general, 1)

        m1 = self._create_media(1, "m1.jpg")
        m2 = self._create_media(2, "m2.jpg")
        m3 = self._create_media(3, "m3.jpg")
        self.db.commit()

        # m1, m2, m3 all have artist_a and char_a (perfect correlation)
        m1.tags = [t_artist, t_char, t_gen]
        m2.tags = [t_artist, t_char]
        m3.tags = [t_artist, t_char, t_other]
        self.db.commit()

        self.index.rebuild(self.db)

        related = self.index.get_related_tags(t_artist.id, limit=5)
        self.assertIsNotNone(related)
        self.assertGreater(len(related), 0)

        # char_a appears in all 3 posts with artist_a -> frequency 1.0, jaccard 1.0
        char_entry = next((item for item in related if item["id"] == t_char.id), None)
        self.assertIsNotNone(char_entry)
        self.assertAlmostEqual(char_entry["frequency"], 1.0)
        self.assertAlmostEqual(char_entry["jaccard_similarity"], 1.0)
        self.assertAlmostEqual(char_entry["overlap_coefficient"], 1.0)
        self.assertEqual(char_entry["co_count"], 3)

        # Test category filter
        general_only = self.index.get_related_tags(t_artist.id, limit=5, category_filter="general")
        self.assertIsNotNone(general_only)
        for item in general_only:
            self.assertEqual(item["category"], "general")

    def test_empty_or_unknown_media(self):
        """Edge cases: unknown media ID, empty index, media with no tags."""
        m1 = self._create_media(1, "m1.jpg")
        self.db.commit()

        # Index empty
        self.index.rebuild(self.db)
        self.assertEqual(self.index.get_similar_media(1), [])
        self.assertEqual(self.index.get_similar_media(999), [])
        self.assertIsNone(self.index.get_related_tags(999))

    def test_concurrent_rebuild_skips(self):
        """Two concurrent rebuild calls: one runs, the second skips without errors or deadlock."""
        import threading

        t1 = self._create_tag(1, "artist_a", TagCategoryEnum.artist, 2)
        m1 = self._create_media(1, "m1.jpg")
        m2 = self._create_media(2, "m2.jpg")
        self.db.commit()
        m1.tags = [t1]
        m2.tags = [t1]
        self.db.commit()

        threads = []
        errors = []

        def run_rebuild():
            try:
                db_session = self.SessionLocal()
                try:
                    self.index.rebuild(db_session)
                finally:
                    db_session.close()
            except Exception as e:
                errors.append(e)

        for _ in range(5):
            t = threading.Thread(target=run_rebuild)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertTrue(self.index.is_ready)
        self.assertFalse(self.index.is_building)

    def test_rebuild_after_data_changes(self):
        """Verify data mutations are accurately reflected in the next snapshot without leaks."""
        t_artist = self._create_tag(1, "artist_a", TagCategoryEnum.artist, 2)
        t_char = self._create_tag(2, "char_a", TagCategoryEnum.character, 1)
        m1 = self._create_media(1, "m1.jpg")
        m2 = self._create_media(2, "m2.jpg")
        m3 = self._create_media(3, "m3.jpg")
        self.db.commit()

        m1.tags = [t_artist]
        m2.tags = [t_artist]
        self.db.commit()

        # Build initial index
        self.index.rebuild(self.db)
        initial_results = self.index.get_similar_media(1, limit=5)
        self.assertEqual(len(initial_results), 1)
        self.assertEqual(initial_results[0][0], 2)

        # Mutate: Add m3 with both artist_a and char_a, and add char_a to m1
        m1.tags = [t_artist, t_char]
        m3.tags = [t_artist, t_char]
        t_char.post_count = 2
        self.db.commit()

        # Rebuild
        self.index.rebuild(self.db)
        updated_results = self.index.get_similar_media(1, limit=5)
        self.assertEqual(len(updated_results), 2)
        # m3 shares both artist and character, so it should rank first
        self.assertEqual(updated_results[0][0], 3)
        self.assertEqual(updated_results[1][0], 2)

    def test_dirty_flag_concurrency(self):
        """Setting dirty = True during an in-flight rebuild must remain True after rebuild."""
        import threading

        t1 = self._create_tag(1, "artist_a", TagCategoryEnum.artist, 2)
        m1 = self._create_media(1, "m1.jpg")
        m2 = self._create_media(2, "m2.jpg")
        self.db.commit()
        m1.tags = [t1]
        m2.tags = [t1]
        self.db.commit()

        # Intercept db.execute to pause during rebuild while setting dirty = True
        original_execute = self.db.execute
        in_flight_event = threading.Event()
        resume_event = threading.Event()

        def slow_execute(*args, **kwargs):
            in_flight_event.set()
            resume_event.wait(timeout=2.0)
            return original_execute(*args, **kwargs)

        self.db.execute = slow_execute

        try:
            rebuild_thread = threading.Thread(target=lambda: self.index.rebuild(self.db))
            rebuild_thread.start()

            # Wait until rebuild has started executing and acquired the building lock
            self.assertTrue(in_flight_event.wait(timeout=2.0))
            self.assertTrue(self.index.is_building)

            # Invalidation arrives while rebuild is actively in-flight
            self.index.dirty = True

            # Let rebuild proceed and complete
            resume_event.set()
            rebuild_thread.join(timeout=2.0)

            # Assert dirty remains True after rebuild finishes
            self.assertTrue(self.index.dirty)
            self.assertTrue(self.index.is_ready)
            self.assertFalse(self.index.is_building)
        finally:
            resume_event.set()
            self.db.execute = original_execute

    def test_large_scale_similarity(self):
        """Test index building and similarity with dozens of media and hundreds of tags."""
        num_media = 60
        num_tags = 150

        media_objs = []
        for i in range(1, num_media + 1):
            media_objs.append(self._create_media(i, f"large_m_{i}.jpg"))

        tag_objs = []
        categories = [
            TagCategoryEnum.artist,
            TagCategoryEnum.character,
            TagCategoryEnum.general,
            TagCategoryEnum.copyright,
            TagCategoryEnum.meta,
        ]
        for j in range(1, num_tags + 1):
            cat = categories[j % len(categories)]
            tag_objs.append(self._create_tag(j, f"tag_{j}", cat, post_count=0))

        self.db.commit()

        # Assign tags with deterministic patterns:
        # Items sharing same i % 5 share common artist/character tags
        for i, m in enumerate(media_objs):
            group = i % 5
            assigned = [
                tag_objs[group],  # Artist/char tag specific to group
                tag_objs[group + 5],  # Another group-specific tag
                tag_objs[10 + (i % 20)],  # General descriptor
                tag_objs[30 + (i % 30)],  # General descriptor
                tag_objs[140],  # Ubiquitous meta tag on all media
            ]
            m.tags = assigned
            for t in assigned:
                t.post_count += 1

        self.db.commit()

        self.index.rebuild(self.db)
        self.assertTrue(self.index.is_ready)

        # Query media in group 0 (e.g. media ID 1, index 0)
        results = self.index.get_similar_media(1, limit=10)
        self.assertGreater(len(results), 0)

        # All top results should belong to group 0 (i.e. media IDs 6, 11, 16, 21, 26, 31, ...)
        for mid, score in results[:5]:
            self.assertEqual((mid - 1) % 5, 0)
            self.assertGreater(score, 0.0)

        # Verify ordering is monotonically non-increasing
        scores = [s for _, s in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

if __name__ == "__main__":
    unittest.main()
