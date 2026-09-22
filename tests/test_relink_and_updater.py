import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from backend.app.config import settings
from backend.app.enums import FileTypeEnum, RatingEnum
from backend.app.models import Media, User
from backend.app.routes.media import PostUpdateRequest, update_from_source, update_file_finalize
from backend.app.utils.file_scanner import relink_media_files
from backend.app.utils.media_processor import calculate_file_hash
from tests.test_base import AsyncBackupTestBase

class TestRelinkAndUpdater(AsyncBackupTestBase):
    def setUp(self):
        super().setUp()
        self.mock_user = User(id=1, username="admin", password_hash="hashed_secret")

    def test_relink_media_files_moves_transcoded_file_without_reprocessing(self):
        """When an original file is moved/renamed, relink_media_files must move/rename
        the existing transcoded file instead of re-transcoding it."""
        # 1. Setup original file in old location
        old_orig_file = self.original_dir / "old_subfolder" / "sample.mkv"
        old_orig_file.parent.mkdir(parents=True, exist_ok=True)
        old_orig_file.write_bytes(b"VIDEO_CONTENT_MKV_123")
        file_hash = calculate_file_hash(old_orig_file)

        # Setup existing transcoded file in old location
        old_trans_file = self.transcoded_dir / "old_subfolder" / "sample.mp4"
        old_trans_file.parent.mkdir(parents=True, exist_ok=True)
        old_trans_file.write_bytes(b"TRANSCODED_MP4_ALREADY_DONE")

        old_thumb_file = self.thumbnail_dir / "old_subfolder" / "sample.jpg"
        old_thumb_file.parent.mkdir(parents=True, exist_ok=True)
        old_thumb_file.write_bytes(b"THUMB_CONTENT")

        media = Media(
            id=1,
            filename="sample.mkv",
            path=str(old_orig_file.relative_to(self.base_path)),
            transcoded_path=str(old_trans_file.relative_to(self.base_path)),
            thumbnail_path=str(old_thumb_file.relative_to(self.base_path)),
            hash=file_hash,
            file_type=FileTypeEnum.video,
            mime_type="video/x-matroska",
            file_size=len(b"VIDEO_CONTENT_MKV_123"),
            rating=RatingEnum.safe,
        )
        self.db.add(media)
        self.db.commit()

        # 2. Simulate user moving the original file to a new folder
        new_orig_file = self.original_dir / "new_folder" / "renamed_sample.mkv"
        new_orig_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_orig_file), str(new_orig_file))

        # 3. Run relink_media_files with transcode_media_if_needed patched to ensure it is NOT called
        with patch.object(settings, "BASE_DIR", self.base_path), \
             patch.object(settings, "ORIGINAL_DIR", self.original_dir), \
             patch.object(settings, "TRANSCODED_DIR", self.transcoded_dir), \
             patch.object(settings, "THUMBNAIL_DIR", self.thumbnail_dir), \
             patch("backend.app.utils.file_scanner.get_mime_type", return_value="video/x-matroska"), \
             patch("backend.app.utils.file_scanner.transcode_media_if_needed") as mock_transcode:

            result = relink_media_files(self.db)
            self.assertEqual(result["relinked"], 1)
            self.assertEqual(result["unresolved"], 0)

            # Assert transcode was NOT called because existing transcoded file was moved
            mock_transcode.assert_not_called()

            # Refresh media record
            self.db.refresh(media)
            self.assertEqual(media.filename, "renamed_sample.mkv")
            self.assertEqual(media.path, str(new_orig_file.relative_to(self.base_path)))

            expected_new_trans = self.transcoded_dir / "new_folder" / "renamed_sample.mp4"
            self.assertEqual(media.transcoded_path, str(expected_new_trans.relative_to(self.base_path)))

            # Verify files on disk
            self.assertTrue(expected_new_trans.exists())
            self.assertEqual(expected_new_trans.read_bytes(), b"TRANSCODED_MP4_ALREADY_DONE")
            self.assertFalse(old_trans_file.exists())

    async def test_update_from_source_renaming_moves_transcoded_file(self):
        """When updating filename via update_from_source, the transcoded file must be moved/renamed."""
        orig_file = self.original_dir / "original_name.mkv"
        orig_file.write_bytes(b"VIDEO_ORIG_BYTES")
        file_hash = calculate_file_hash(orig_file)

        trans_file = self.transcoded_dir / "original_name.mp4"
        trans_file.write_bytes(b"TRANSCODED_CONTENT")

        thumb_file = self.thumbnail_dir / "original_name.jpg"
        thumb_file.write_bytes(b"THUMB_CONTENT")

        media = Media(
            id=2,
            filename="original_name.mkv",
            path=str(orig_file.relative_to(self.base_path)),
            transcoded_path=str(trans_file.relative_to(self.base_path)),
            thumbnail_path=str(thumb_file.relative_to(self.base_path)),
            hash=file_hash,
            file_type=FileTypeEnum.video,
            mime_type="video/x-matroska",
            file_size=len(b"VIDEO_ORIG_BYTES"),
            rating=RatingEnum.safe,
        )
        self.db.add(media)
        self.db.commit()

        req = PostUpdateRequest(
            update_filename=True,
            filename="renamed_target.mkv"
        )

        with patch.object(settings, "BASE_DIR", self.base_path), \
             patch.object(settings, "ORIGINAL_DIR", self.original_dir), \
             patch.object(settings, "TRANSCODED_DIR", self.transcoded_dir), \
             patch.object(settings, "THUMBNAIL_DIR", self.thumbnail_dir):

            resp = await update_from_source(
                media_id=2,
                req=req,
                current_user=self.mock_user,
                db=self.db,
            )

            self.assertEqual(resp.filename, "renamed_target.mkv")
            self.db.refresh(media)

            expected_new_orig = self.original_dir / "renamed_target.mkv"
            expected_new_trans = self.transcoded_dir / "renamed_target.mp4"
            expected_new_thumb = self.thumbnail_dir / "renamed_target.jpg"

            self.assertEqual(media.path, str(expected_new_orig.relative_to(self.base_path)))
            self.assertEqual(media.transcoded_path, str(expected_new_trans.relative_to(self.base_path)))
            self.assertEqual(media.thumbnail_path, str(expected_new_thumb.relative_to(self.base_path)))

            self.assertTrue(expected_new_orig.exists())
            self.assertTrue(expected_new_trans.exists())
            self.assertEqual(expected_new_trans.read_bytes(), b"TRANSCODED_CONTENT")
            self.assertFalse(trans_file.exists())

    async def test_update_from_source_replace_file_updates_transcode(self):
        """When replacing a media file via update_from_source, old transcode is cleaned and new one is generated."""
        orig_file = self.original_dir / "photo.heic"
        orig_file.write_bytes(b"OLD_HEIC_BYTES")
        file_hash = calculate_file_hash(orig_file)

        old_trans_file = self.transcoded_dir / "photo.webp"
        old_trans_file.write_bytes(b"OLD_TRANSCODED_WEBP")

        media = Media(
            id=3,
            filename="photo.heic",
            path=str(orig_file.relative_to(self.base_path)),
            transcoded_path=str(old_trans_file.relative_to(self.base_path)),
            hash=file_hash,
            file_type=FileTypeEnum.image,
            mime_type="image/heic",
            file_size=len(b"OLD_HEIC_BYTES"),
            rating=RatingEnum.safe,
        )
        self.db.add(media)
        self.db.commit()

        # Mock download of new HEIC image
        new_img_bytes = b"NEW_DOWNLOADED_BYTES"

        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [new_img_bytes]
        mock_resp.raise_for_status.return_value = None

        req = PostUpdateRequest(
            update_file=True,
            file_url="https://example.com/new_photo.heic"
        )

        with patch.object(settings, "BASE_DIR", self.base_path), \
             patch.object(settings, "ORIGINAL_DIR", self.original_dir), \
             patch.object(settings, "TRANSCODED_DIR", self.transcoded_dir), \
             patch.object(settings, "THUMBNAIL_DIR", self.thumbnail_dir), \
             patch("requests.get", return_value=mock_resp), \
             patch("backend.app.routes.media.process_media_file") as mock_process, \
             patch("backend.app.routes.media.generate_thumbnail", return_value=True):

            mock_process.return_value = {
                "file_type": FileTypeEnum.image,
                "mime_type": "image/heic",
                "file_size": len(new_img_bytes),
                "transcoded_path": "media/transcoded/photo.webp",
                "width": 800,
                "height": 600,
                "duration": None,
            }

            resp = await update_from_source(
                media_id=3,
                req=req,
                current_user=self.mock_user,
                db=self.db,
            )

            self.db.refresh(media)
            self.assertEqual(media.transcoded_path, "media/transcoded/photo.webp")
            self.assertEqual(media.width, 800)

    def test_backup_import_transcodes_non_web_media(self):
        """When restoring a backup, non-web media must be transcoded and saved with transcoded_path."""
        import io
        import json
        import zipfile
        from backend.app.utils.backup import import_full_backup

        # Prepare in-memory ZIP with backup.json and media/test.mkv
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            backup_meta = {
                "version": "1.41.0-rc.2",
                "schema_version": 8,
                "media": [
                    {
                        "filename": "test.mkv",
                        "hash": "mkv_hash_123",
                        "file_type": "video",
                        "mime_type": "video/x-matroska",
                        "file_size": 100,
                        "rating": "safe",
                        "archive_path": "media/test.mkv",
                    }
                ]
            }
            zf.writestr("backup.json", json.dumps(backup_meta))
            zf.writestr("media/test.mkv", b"SAMPLE_MKV_BYTES_BACKUP")

        zip_buffer.seek(0)

        with patch.object(settings, "BASE_DIR", self.base_path), \
             patch.object(settings, "ORIGINAL_DIR", self.original_dir), \
             patch.object(settings, "TRANSCODED_DIR", self.transcoded_dir), \
             patch.object(settings, "THUMBNAIL_DIR", self.thumbnail_dir), \
             patch("backend.app.utils.backup.transcode_media_if_needed") as mock_transcode, \
             patch("backend.app.utils.backup.generate_thumbnail", return_value=True):

            expected_trans = self.transcoded_dir / "test.mp4"
            mock_transcode.return_value = expected_trans

            res = import_full_backup(zip_buffer, self.db)
            self.assertEqual(res["stats"]["media"]["imported"], 1)

            imported = self.db.query(Media).filter(Media.hash == "mkv_hash_123").first()
            self.assertIsNotNone(imported)
            self.assertEqual(imported.transcoded_path, str(expected_trans.relative_to(self.base_path)))
            mock_transcode.assert_called_once()

    async def test_update_file_finalize_keep_filename(self):
        """Finalizing an update with update_filename=False retains original filename."""
        import json as _json
        orig_file = self.original_dir / "sample_orig.png"
        orig_file.write_bytes(b"INITIAL_ORIG_BYTES")
        old_hash = calculate_file_hash(orig_file)

        media = Media(
            id=10,
            filename="sample_orig.png",
            path="media/original/sample_orig.png",
            hash=old_hash,
            file_type=FileTypeEnum.image,
            mime_type="image/png",
            file_size=len(b"INITIAL_ORIG_BYTES"),
            rating=RatingEnum.safe,
        )
        self.db.add(media)
        self.db.commit()

        upload_id = "11111111-2222-3333-4444-555555555555"
        chunk_dir = self.chunks_dir / upload_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        (chunk_dir / "meta.json").write_text(_json.dumps({"filename": "new_device_name.png", "total_chunks": 1}))
        (chunk_dir / "chunk_0").write_bytes(b"NEW_DEVICE_BYTES_CONTENT")

        with patch.object(settings, "BASE_DIR", self.base_path), \
             patch.object(settings, "ORIGINAL_DIR", self.original_dir), \
             patch.object(settings, "TRANSCODED_DIR", self.transcoded_dir), \
             patch.object(settings, "THUMBNAIL_DIR", self.thumbnail_dir), \
             patch("backend.app.routes.media.MEDIA_CHUNKS_DIR", self.chunks_dir), \
             patch("backend.app.routes.media.process_media_file") as mock_process, \
             patch("backend.app.routes.media.generate_thumbnail", return_value=True):

            mock_process.side_effect = lambda f, precalculated_hash=None: {
                "file_type": FileTypeEnum.image,
                "mime_type": "image/png",
                "file_size": f.stat().st_size,
                "transcoded_path": None,
                "width": 2048,
                "height": 1536,
                "duration": None,
            }

            resp = await update_file_finalize(
                media_id=10,
                upload_id=upload_id,
                update_filename=False,
                current_user=self.mock_user,
                db=self.db,
            )

            self.db.refresh(media)
            self.assertEqual(media.filename, "sample_orig.png")
            self.assertEqual(media.path, "media/original/sample_orig.png")
            self.assertEqual(media.width, 2048)
            self.assertTrue(orig_file.exists())
            self.assertEqual(orig_file.read_bytes(), b"NEW_DEVICE_BYTES_CONTENT")

    async def test_update_file_finalize_update_filename(self):
        """Finalizing an update with update_filename=True updates filename and storage path."""
        import json as _json
        orig_file = self.original_dir / "sample_orig2.png"
        orig_file.write_bytes(b"INITIAL_ORIG_BYTES_2")
        old_hash = calculate_file_hash(orig_file)

        media = Media(
            id=11,
            filename="sample_orig2.png",
            path="media/original/sample_orig2.png",
            hash=old_hash,
            file_type=FileTypeEnum.image,
            mime_type="image/png",
            file_size=len(b"INITIAL_ORIG_BYTES_2"),
            rating=RatingEnum.safe,
        )
        self.db.add(media)
        self.db.commit()

        upload_id = "22222222-3333-4444-5555-666666666666"
        chunk_dir = self.chunks_dir / upload_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        (chunk_dir / "meta.json").write_text(_json.dumps({"filename": "brand_new_name.png", "total_chunks": 1}))
        (chunk_dir / "chunk_0").write_bytes(b"BRAND_NEW_CONTENT_BYTES")

        with patch.object(settings, "BASE_DIR", self.base_path), \
             patch.object(settings, "ORIGINAL_DIR", self.original_dir), \
             patch.object(settings, "TRANSCODED_DIR", self.transcoded_dir), \
             patch.object(settings, "THUMBNAIL_DIR", self.thumbnail_dir), \
             patch("backend.app.routes.media.MEDIA_CHUNKS_DIR", self.chunks_dir), \
             patch("backend.app.routes.media.process_media_file") as mock_process, \
             patch("backend.app.routes.media.generate_thumbnail", return_value=True):

            mock_process.side_effect = lambda f, precalculated_hash=None: {
                "file_type": FileTypeEnum.image,
                "mime_type": "image/png",
                "file_size": f.stat().st_size,
                "transcoded_path": None,
                "width": 1000,
                "height": 1000,
                "duration": None,
            }

            resp = await update_file_finalize(
                media_id=11,
                upload_id=upload_id,
                update_filename=True,
                current_user=self.mock_user,
                db=self.db,
            )

            self.db.refresh(media)
            self.assertEqual(media.filename, "brand_new_name.png")
            self.assertEqual(media.path, "media/original/brand_new_name.png")
            self.assertFalse(orig_file.exists())
            new_file = self.original_dir / "brand_new_name.png"
            self.assertTrue(new_file.exists())
            self.assertEqual(new_file.read_bytes(), b"BRAND_NEW_CONTENT_BYTES")

    async def test_update_file_finalize_extension_change_when_keep_filename(self):
        """When keeping filename but replacing with different format, stem is preserved with updated extension."""
        import json as _json
        orig_file = self.original_dir / "keep_my_name.png"
        orig_file.write_bytes(b"INITIAL_PNG_BYTES")
        old_hash = calculate_file_hash(orig_file)

        media = Media(
            id=12,
            filename="keep_my_name.png",
            path="media/original/keep_my_name.png",
            hash=old_hash,
            file_type=FileTypeEnum.image,
            mime_type="image/png",
            file_size=len(b"INITIAL_PNG_BYTES"),
            rating=RatingEnum.safe,
        )
        self.db.add(media)
        self.db.commit()

        upload_id = "33333333-4444-5555-6666-777777777777"
        chunk_dir = self.chunks_dir / upload_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        (chunk_dir / "meta.json").write_text(_json.dumps({"filename": "incoming_upload.mp4", "total_chunks": 1}))
        (chunk_dir / "chunk_0").write_bytes(b"NEW_VIDEO_CONTENT")

        with patch.object(settings, "BASE_DIR", self.base_path), \
             patch.object(settings, "ORIGINAL_DIR", self.original_dir), \
             patch.object(settings, "TRANSCODED_DIR", self.transcoded_dir), \
             patch.object(settings, "THUMBNAIL_DIR", self.thumbnail_dir), \
             patch("backend.app.routes.media.MEDIA_CHUNKS_DIR", self.chunks_dir), \
             patch("backend.app.routes.media.process_media_file") as mock_process, \
             patch("backend.app.routes.media.generate_thumbnail", return_value=True):

            mock_process.side_effect = lambda f, precalculated_hash=None: {
                "file_type": FileTypeEnum.video,
                "mime_type": "video/mp4",
                "file_size": f.stat().st_size,
                "transcoded_path": None,
                "width": 1920,
                "height": 1080,
                "duration": 12.5,
            }

            resp = await update_file_finalize(
                media_id=12,
                upload_id=upload_id,
                update_filename=False,
                current_user=self.mock_user,
                db=self.db,
            )

            self.db.refresh(media)
            self.assertEqual(media.filename, "keep_my_name.mp4")
            self.assertEqual(media.path, "media/original/keep_my_name.mp4")
            self.assertFalse(orig_file.exists())
            new_file = self.original_dir / "keep_my_name.mp4"
            self.assertTrue(new_file.exists())
            self.assertEqual(new_file.read_bytes(), b"NEW_VIDEO_CONTENT")

    async def test_update_file_finalize_transcodes_if_needed(self):
        """Finalizing with a format requiring transcoding properly updates transcoded_path."""
        import json as _json
        orig_file = self.original_dir / "photo.jpg"
        orig_file.write_bytes(b"INITIAL_JPG_BYTES")
        old_hash = calculate_file_hash(orig_file)

        media = Media(
            id=13,
            filename="photo.jpg",
            path="media/original/photo.jpg",
            hash=old_hash,
            file_type=FileTypeEnum.image,
            mime_type="image/jpeg",
            file_size=len(b"INITIAL_JPG_BYTES"),
            rating=RatingEnum.safe,
        )
        self.db.add(media)
        self.db.commit()

        upload_id = "44444444-5555-6666-7777-888888888888"
        chunk_dir = self.chunks_dir / upload_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        (chunk_dir / "meta.json").write_text(_json.dumps({"filename": "video.mkv", "total_chunks": 1}))
        (chunk_dir / "chunk_0").write_bytes(b"MKV_RAW_BYTES")

        transcoded_target = self.transcoded_dir / "photo.mp4"
        transcoded_target.write_bytes(b"TRANSCODED_MP4_BYTES")

        with patch.object(settings, "BASE_DIR", self.base_path), \
             patch.object(settings, "ORIGINAL_DIR", self.original_dir), \
             patch.object(settings, "TRANSCODED_DIR", self.transcoded_dir), \
             patch.object(settings, "THUMBNAIL_DIR", self.thumbnail_dir), \
             patch("backend.app.routes.media.MEDIA_CHUNKS_DIR", self.chunks_dir), \
             patch("backend.app.routes.media.process_media_file") as mock_process, \
             patch("backend.app.routes.media.generate_thumbnail", return_value=True):

            mock_process.side_effect = lambda f, precalculated_hash=None: {
                "file_type": FileTypeEnum.video,
                "mime_type": "video/x-matroska",
                "file_size": f.stat().st_size,
                "transcoded_path": str(transcoded_target.relative_to(self.base_path)),
                "width": 1280,
                "height": 720,
                "duration": 5.0,
            }

            resp = await update_file_finalize(
                media_id=13,
                upload_id=upload_id,
                update_filename=False,
                current_user=self.mock_user,
                db=self.db,
            )

            self.db.refresh(media)
            self.assertEqual(media.filename, "photo.mkv")
            self.assertEqual(media.transcoded_path, str(transcoded_target.relative_to(self.base_path)))
            self.assertEqual(media.width, 1280)
            self.assertEqual(media.height, 720)

if __name__ == "__main__":
    unittest.main()

