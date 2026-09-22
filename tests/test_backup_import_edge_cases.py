import io
import json
import unittest
import zipfile

from fastapi import HTTPException

from backend.app.enums import FileTypeEnum, RatingEnum
from backend.app.models import Album, BooruConfig, Media, TagImplication
from backend.app.utils.backup import import_full_backup
from tests.test_base import BackupTestBase, make_dummy_jpeg

class TestBackupImportEdgeCases(BackupTestBase):
    def test_duplicate_media_hash_skipped(self):
        """Test that media with already existing hashes in DB are skipped during import."""
        dummy_jpeg = make_dummy_jpeg()
        # Pre-insert existing media in DB
        m_existing = Media(
            filename="original_m1.jpg",
            path=str(self.original_dir / "original_m1.jpg"),
            hash="duplicate_hash_123",
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            file_size=len(dummy_jpeg),
            rating=RatingEnum.safe
        )
        self.db.add(m_existing)
        self.db.commit()

        # Backup contains duplicate_hash_123 and brand_new_hash_456
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("tags.csv", "tag1,0,0,\n")
            meta = {
                "type": "full_backup",
                "media": [
                    {
                        "filename": "duplicate_attempt.jpg",
                        "hash": "duplicate_hash_123",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "archive_path": "media/dup.jpg"
                    },
                    {
                        "filename": "brand_new.jpg",
                        "hash": "brand_new_hash_456",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "archive_path": "media/brand_new.jpg"
                    }
                ]
            }
            zf.writestr("backup.json", json.dumps(meta))
            zf.writestr("media/dup.jpg", dummy_jpeg)
            zf.writestr("media/brand_new.jpg", dummy_jpeg)

        zip_buffer.seek(0)
        result = import_full_backup(zip_buffer, self.db)
        self.assertEqual(result["stats"]["media"]["skipped"], 1)
        self.assertEqual(result["stats"]["media"]["imported"], 1)

        # Verify existing media filename remains unaltered
        m_check = self.db.query(Media).filter(Media.hash == "duplicate_hash_123").first()
        self.assertEqual(m_check.filename, "original_m1.jpg")

        # Verify new media was created
        m_new = self.db.query(Media).filter(Media.hash == "brand_new_hash_456").first()
        self.assertIsNotNone(m_new)
        self.assertEqual(m_new.filename, "brand_new.jpg")

    def test_media_fallback_filename_matching(self):
        """Test that media files are found by filename fallback when archive_path is missing or mismatched."""
        dummy_jpeg = make_dummy_jpeg()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("tags.csv", "tag1,0,0,\n")
            meta = {
                "type": "full_backup",
                "media": [
                    {
                        "filename": "fallback_photo.jpg",
                        "hash": "fallback_hash_789",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "archive_path": "media/non_existent_folder/missing.jpg"
                    }
                ]
            }
            zf.writestr("backup.json", json.dumps(meta))
            # File stored under media/fallback_photo.jpg (matches original filename)
            zf.writestr("media/fallback_photo.jpg", dummy_jpeg)

        zip_buffer.seek(0)
        result = import_full_backup(zip_buffer, self.db)
        self.assertEqual(result["stats"]["media"]["imported"], 1)
        m = self.db.query(Media).filter(Media.hash == "fallback_hash_789").first()
        self.assertIsNotNone(m)
        self.assertEqual(m.filename, "fallback_photo.jpg")

    def test_invalid_archive_handling(self):
        """Test that non-ZIP data and empty backup archives raise HTTPException(400)."""
        # 1. Non-zip data
        not_a_zip = io.BytesIO(b"this is plainly not a zip archive")
        with self.assertRaises(HTTPException) as ctx:
            import_full_backup(not_a_zip, self.db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Invalid ZIP file")

        # 2. ZIP with neither tags.csv nor backup.json
        empty_zip = io.BytesIO()
        with zipfile.ZipFile(empty_zip, 'w') as zf:
            zf.writestr("readme.txt", "nothing here")
        empty_zip.seek(0)
        with self.assertRaises(HTTPException) as ctx:
            import_full_backup(empty_zip, self.db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("No valid backup data found", ctx.exception.detail)

    def test_corrupted_json_archive_handling(self):
        """Test that backup archives containing truncated or invalid backup.json raise HTTPException(400)."""
        corrupted_zip = io.BytesIO()
        with zipfile.ZipFile(corrupted_zip, 'w') as zf:
            zf.writestr("tags.csv", "safe_tag,0,0,\n")
            # Truncated invalid JSON content
            zf.writestr("backup.json", '{"type": "full_backup", "media": [{"hash": "123", ')
        corrupted_zip.seek(0)

        with self.assertRaises(HTTPException) as ctx:
            import_full_backup(corrupted_zip, self.db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Error parsing backup.json", ctx.exception.detail)

    def test_booru_config_normalization_and_update(self):
        """Test that booru domains are normalized (scheme/trailing slash stripped) and existing configs updated."""
        # Pre-insert existing config
        existing_cfg = BooruConfig(
            domain="danbooru.donmai.us",
            username="old_admin",
            api_key="old_api_key"
        )
        self.db.add(existing_cfg)
        self.db.commit()

        # Import backup with scheme:// and trailing slash
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("tags.csv", "tag1,0,0,\n")
            meta = {
                "type": "full_backup",
                "booru_config": [
                    {
                        "domain": "https://danbooru.donmai.us/",
                        "username": "updated_admin",
                        "api_key": "new_api_key"
                    },
                    {
                        "domain": "http://gelbooru.com/",
                        "username": "gel_user",
                        "api_key": "gel_key"
                    }
                ]
            }
            zf.writestr("backup.json", json.dumps(meta))

        zip_buffer.seek(0)
        result = import_full_backup(zip_buffer, self.db)
        self.assertEqual(result["stats"]["booru_config"]["imported"], 2)

        # Verify danbooru was updated in place (no duplicate row)
        dan_cfgs = self.db.query(BooruConfig).filter(BooruConfig.domain == "danbooru.donmai.us").all()
        self.assertEqual(len(dan_cfgs), 1)
        self.assertEqual(dan_cfgs[0].username, "updated_admin")
        self.assertEqual(dan_cfgs[0].api_key, "new_api_key")

        # Verify gelbooru was created with normalized domain
        gel_cfg = self.db.query(BooruConfig).filter(BooruConfig.domain == "gelbooru.com").first()
        self.assertIsNotNone(gel_cfg)
        self.assertEqual(gel_cfg.username, "gel_user")

    def test_tag_implication_deduplication(self):
        """Test that importing duplicate tag implication rules increments skipped count and avoids duplicates."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("tags.csv", "kitsune,0,0,\nfox_ears,0,0,\nanimal_ears,0,0,\n")
            meta = {
                "type": "full_backup",
                "tag_implications": [
                    {
                        "target_tags": ["kitsune"],
                        "target_tag_patterns": ["*_fox"],
                        "implied_tags": ["fox_ears", "animal_ears"]
                    }
                ]
            }
            zf.writestr("backup.json", json.dumps(meta))

        # First import
        zip_buffer.seek(0)
        res1 = import_full_backup(zip_buffer, self.db)
        self.assertEqual(res1["stats"]["tag_implications"]["imported"], 1)
        self.assertEqual(res1["stats"]["tag_implications"]["skipped"], 0)
        self.assertEqual(self.db.query(TagImplication).count(), 1)

        # Second import (re-import)
        zip_buffer.seek(0)
        res2 = import_full_backup(zip_buffer, self.db)
        self.assertEqual(res2["stats"]["tag_implications"]["imported"], 0)
        self.assertEqual(res2["stats"]["tag_implications"]["skipped"], 1)
        self.assertEqual(self.db.query(TagImplication).count(), 1)

    def test_album_name_collision_merge(self):
        """Test that backup albums with names matching existing DB albums merge cleanly."""
        dummy_jpeg = make_dummy_jpeg()
        # Pre-insert existing album in DB with media m1
        m1 = Media(
            filename="m1.jpg",
            path=str(self.original_dir / "m1.jpg"),
            hash="hash_m1",
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            file_size=len(dummy_jpeg)
        )
        self.db.add(m1)
        self.db.commit()

        alb_existing = Album(name="Scenery")
        alb_existing.media.append(m1)
        self.db.add(alb_existing)
        self.db.commit()
        existing_alb_id = alb_existing.id

        # Backup contains an album named "Scenery" with media m2
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("tags.csv", "scenery_tag,0,0,\n")
            meta = {
                "type": "full_backup",
                "media": [
                    {
                        "filename": "m2.jpg",
                        "hash": "hash_m2",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "file_size": len(dummy_jpeg),
                        "archive_path": "media/m2.jpg"
                    }
                ],
                "albums": [
                    {
                        "id": 999,
                        "name": "Scenery",
                        "media": [
                            {"hash": "hash_m2"}
                        ]
                    }
                ]
            }
            zf.writestr("backup.json", json.dumps(meta))
            zf.writestr("media/m2.jpg", dummy_jpeg)

        zip_buffer.seek(0)
        result = import_full_backup(zip_buffer, self.db)
        self.assertEqual(result["stats"]["albums"]["albums_created"], 0)
        self.assertEqual(result["stats"]["albums"]["albums_existing"], 1)

        # Verify only 1 album exists with name "Scenery"
        albums = self.db.query(Album).filter(Album.name == "Scenery").all()
        self.assertEqual(len(albums), 1)
        self.assertEqual(albums[0].id, existing_alb_id)
        self.assertEqual(len(albums[0].media), 2)

    def test_media_parent_hash_absent(self):
        """Test that media referencing a non-existent parent_hash imports successfully with parent_id as None."""
        dummy_jpeg = make_dummy_jpeg()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("tags.csv", "tag1,0,0,\n")
            meta = {
                "type": "full_backup",
                "media": [
                    {
                        "filename": "child.jpg",
                        "hash": "child_hash_123",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "file_size": len(dummy_jpeg),
                        "parent_hash": "non_existent_parent_hash_999",
                        "archive_path": "media/child.jpg"
                    }
                ]
            }
            zf.writestr("backup.json", json.dumps(meta))
            zf.writestr("media/child.jpg", dummy_jpeg)

        zip_buffer.seek(0)
        result = import_full_backup(zip_buffer, self.db)
        self.assertEqual(result["stats"]["media"]["imported"], 1)
        m = self.db.query(Media).filter(Media.hash == "child_hash_123").first()
        self.assertIsNotNone(m)
        self.assertIsNone(m.parent_id)

if __name__ == "__main__":
    unittest.main()
