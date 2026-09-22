import unittest

from backend.app.enums import TagCategoryEnum
from backend.app.models import Tag, TagAlias
from backend.app.routes.admin.tags import import_tags_csv_logic
from backend.app.utils.backup import generate_tags_csv_stream, generate_tags_dump
from tests.test_base import BackupTestBase

class TestBackupTags(BackupTestBase):
    def test_generate_tags_csv_stream_and_import(self):
        """Test generating tags CSV and importing it back."""
        t1 = Tag(name="landscape", category=TagCategoryEnum.general, post_count=5)
        t2 = Tag(name="artist_name", category=TagCategoryEnum.artist, post_count=10)
        self.db.add_all([t1, t2])
        self.db.commit()

        a1 = TagAlias(alias_name="scenery", target_tag_id=t1.id)
        a2 = TagAlias(alias_name="nature,view", target_tag_id=t1.id)  # Contains comma
        self.db.add_all([a1, a2])
        self.db.commit()

        # Generate stream
        csv_chunks = list(generate_tags_csv_stream(self.db))
        csv_content = "".join(csv_chunks)

        self.assertIn("landscape,0,5,", csv_content)
        self.assertIn("artist_name,1,10,", csv_content)
        self.assertIn('"scenery,nature,view"', csv_content)  # Quoted comma-separated aliases

        # Wipe and import back
        self.wipe_database()
        import_tags_csv_logic(csv_content, self.db)

        # Verify restoration
        restored_t1 = self.db.query(Tag).filter(Tag.name == "landscape").first()
        self.assertIsNotNone(restored_t1)
        self.assertEqual(restored_t1.category, TagCategoryEnum.general)

        aliases = [a.alias_name for a in restored_t1.aliases]
        self.assertIn("scenery", aliases)
        self.assertIn("nature", aliases)
        self.assertIn("view", aliases)

    def test_generate_tags_dump(self):
        """Test generating tag dump dictionary."""
        t1 = Tag(name="cat", category=TagCategoryEnum.character, post_count=3)
        self.db.add(t1)
        self.db.commit()

        a1 = TagAlias(alias_name="kitty", target_tag_id=t1.id)
        self.db.add(a1)
        self.db.commit()

        dump = generate_tags_dump(self.db)
        self.assertEqual(dump["type"], "tags_dump")
        self.assertTrue(any(t["name"] == "cat" for t in dump["tags"]))
        self.assertTrue(any(a["alias_name"] == "kitty" for a in dump["aliases"]))

    def test_tags_csv_edge_cases(self):
        """Test CSV tag import handling of invalid category, whitespace padding, empty lines, and long tag names."""
        csv_content = (
            '  spaced_tag  ,0,1,"  alias_a , alias_b  "\n'
            "invalid_cat_tag,999,0,\n"
            "bad_cat_string,not_an_int,0,\n"
            "\n"
            f"{'x' * 300},0,0,\n"
            "valid_tag,1,0,\n"
        )
        stats = import_tags_csv_logic(csv_content, self.db)

        self.assertGreaterEqual(stats["tags_created"], 3)
        self.assertEqual(stats["skipped_long_tags"], 1)
        self.assertTrue(any(e.get("key") == "notifications.admin.error_invalid_category" for e in stats["errors"]))

        # Verify spaced_tag was trimmed
        t_spaced = self.db.query(Tag).filter(Tag.name == "spaced_tag").first()
        self.assertIsNotNone(t_spaced)

        # Verify aliases were trimmed and linked
        aliases = [a.alias_name for a in t_spaced.aliases]
        self.assertIn("alias_a", aliases)
        self.assertIn("alias_b", aliases)

        # Verify invalid_cat_tag defaulted to general (category 0)
        t_inv = self.db.query(Tag).filter(Tag.name == "invalid_cat_tag").first()
        self.assertIsNotNone(t_inv)
        self.assertEqual(t_inv.category, TagCategoryEnum.general)

if __name__ == "__main__":
    unittest.main()
