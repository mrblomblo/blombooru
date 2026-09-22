import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import create_engine, inspect, text

from backend.app.config import settings
from backend.app.database import migrate_add_transcoded_path
from backend.app.enums import FileTypeEnum, RatingEnum
from backend.app.models import Media
from backend.app.routes.media import get_media_file
from backend.app.utils.media_helpers import serve_media_file
from tests.test_base import AsyncBackupTestBase

class TestMediaServingAndTranscoding(AsyncBackupTestBase):

    def test_migration_adds_transcoded_path_column(self):
        # Create table without transcoded_path using raw SQL to test migration
        temp_engine = create_engine("sqlite:///:memory:")
        with temp_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE blombooru_media (
                    id INTEGER PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    path VARCHAR(500) NOT NULL
                )
            """))
            conn.commit()

        inspector = inspect(temp_engine)
        columns_before = [c["name"] for c in inspector.get_columns("blombooru_media")]
        self.assertNotIn("transcoded_path", columns_before)

        # Run migration
        migrate_add_transcoded_path(temp_engine, inspector)

        # Verify column exists after migration
        inspector_after = inspect(temp_engine)
        columns_after = [c["name"] for c in inspector_after.get_columns("blombooru_media")]
        self.assertIn("transcoded_path", columns_after)

        # Re-running migration is idempotent
        migrate_add_transcoded_path(temp_engine, inspector_after)

    async def test_serve_media_file_download_header(self):
        test_file = self.base_path / "original_movie.mkv"
        test_file.write_bytes(b"ORIGINAL_MKV_BYTES")

        # Test download=True sets attachment header
        response = await serve_media_file(
            test_file,
            "video/x-matroska",
            download=True,
            filename="custom_name.mkv"
        )
        self.assertEqual(response.headers.get("content-disposition"), 'attachment; filename="custom_name.mkv"')

    async def test_serve_media_file_inline_view(self):
        test_file = self.base_path / "view_image.webp"
        test_file.write_bytes(b"WEBP_BYTES")

        # Test download=False sets inline/default behavior
        response = await serve_media_file(
            test_file,
            "image/webp",
            download=False
        )
        self.assertNotEqual(response.headers.get("content-disposition"), "attachment")

    async def test_serve_media_file_missing_file_raises_404(self):
        missing_file = self.base_path / "non_existent.jpg"
        with self.assertRaises(HTTPException) as ctx:
            await serve_media_file(missing_file, "image/jpeg")
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("backend.app.routes.media.get_db")
    async def test_get_media_file_route_serves_transcoded_for_view(self, mock_get_db):
        # Create media with both path and transcoded_path
        orig_file = self.base_path / "orig_clip.mkv"
        orig_file.write_bytes(b"ORIGINAL_MKV_VIDEO_DATA")
        
        trans_file = self.base_path / "trans_clip.mp4"
        trans_file.write_bytes(b"TRANSCODED_MP4_VIDEO_DATA")

        rel_orig = orig_file.relative_to(self.base_path)
        rel_trans = trans_file.relative_to(self.base_path)

        media = Media(
            id=42,
            filename="orig_clip.mkv",
            path=str(rel_orig),
            transcoded_path=str(rel_trans),
            hash="testhash42",
            file_type=FileTypeEnum.video,
            mime_type="video/x-matroska",
            file_size=1000,
        )
        self.db.add(media)
        self.db.commit()

        mock_get_db.side_effect = lambda: iter([self.db])

        with patch.object(settings, "BASE_DIR", self.base_path):
            # 1. Normal view request (download=False) -> should serve transcoded file
            view_resp = await get_media_file(media_id=42, chunked=False, download=False)
            self.assertEqual(Path(view_resp.path), trans_file)
            self.assertEqual(view_resp.media_type, "video/mp4")

            # 2. Download request (download=True) -> must strictly serve original file
            down_resp = await get_media_file(media_id=42, chunked=False, download=True)
            self.assertEqual(Path(down_resp.path), orig_file)
            self.assertEqual(down_resp.media_type, "video/x-matroska")
            self.assertEqual(down_resp.headers.get("content-disposition"), 'attachment; filename="orig_clip.mkv"')

if __name__ == "__main__":
    unittest.main()
