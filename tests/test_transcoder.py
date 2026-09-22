import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from backend.app.config import settings
from backend.app.enums import FileTypeEnum, RatingEnum
from backend.app.models import Media
from backend.app.schemas import MediaResponse
from backend.app.utils.media_processor import process_media_file
from backend.app.utils.transcoder import (
    get_transcoded_path_for_original,
    transcode_image,
    transcode_media_if_needed,
    transcode_video,
)
from tests.test_base import BackupTestBase

class TestTranscoderComprehensive(BackupTestBase):

    # --- Path Resolution & Hierarchy Preservation Tests ---

    def test_transcoded_path_deeply_nested_subfolders(self):
        orig_nested = settings.ORIGINAL_DIR / "2026" / "08" / "vacation" / "clip.mkv"
        trans_nested = get_transcoded_path_for_original(orig_nested, ".mp4")
        expected = (settings.TRANSCODED_DIR / "2026" / "08" / "vacation" / "clip.mp4").resolve()
        self.assertEqual(trans_nested, expected)

    def test_transcoded_path_root_original_folder(self):
        orig_file = settings.ORIGINAL_DIR / "standalone.heic"
        trans_file = get_transcoded_path_for_original(orig_file, ".webp")
        expected = (settings.TRANSCODED_DIR / "standalone.webp").resolve()
        self.assertEqual(trans_file, expected)

    def test_transcoded_path_outside_original_dir_fallback(self):
        external_file = Path("/tmp/outside/nested/file.avi")
        trans_file = get_transcoded_path_for_original(external_file, ".mp4")
        expected = (settings.TRANSCODED_DIR / "file.mp4").resolve()
        self.assertEqual(trans_file, expected)

    # --- Image Transcoding Color Modes & Metadata Tests ---

    def test_transcode_image_rgb(self):
        src = self.base_path / "rgb_test.heic"
        with Image.new("RGB", (200, 100), color=(255, 128, 64)) as img:
            img.save(src, "PNG")

        dest = self.base_path / "rgb_out.webp"
        self.assertTrue(transcode_image(src, dest))
        self.assertTrue(dest.exists())
        with Image.open(dest) as out:
            self.assertEqual(out.format, "WEBP")
            self.assertEqual(out.size, (200, 100))

    def test_transcode_image_rgba_preserves_transparency(self):
        src = self.base_path / "rgba_test.heic"
        with Image.new("RGBA", (150, 150), color=(0, 0, 255, 128)) as img:
            img.save(src, "PNG")

        dest = self.base_path / "rgba_out.webp"
        self.assertTrue(transcode_image(src, dest))
        self.assertTrue(dest.exists())
        with Image.open(dest) as out:
            self.assertEqual(out.format, "WEBP")
            self.assertEqual(out.mode, "RGBA")

    def test_transcode_image_palette_mode(self):
        src = self.base_path / "palette_test.heic"
        with Image.new("P", (80, 80)) as img:
            img.save(src, "PNG")

        dest = self.base_path / "palette_out.webp"
        self.assertTrue(transcode_image(src, dest))
        self.assertTrue(dest.exists())

    def test_transcode_image_grayscale(self):
        src = self.base_path / "gray_test.heic"
        with Image.new("L", (100, 100), color=128) as img:
            img.save(src, "PNG")

        dest = self.base_path / "gray_out.webp"
        self.assertTrue(transcode_image(src, dest))
        self.assertTrue(dest.exists())

    def test_transcode_image_corrupt_file_cleans_up_temp(self):
        corrupt_src = self.base_path / "corrupt.heic"
        with open(corrupt_src, "wb") as f:
            f.write(b"NOT_A_VALID_IMAGE_DATA_CORRUPT")

        dest = self.base_path / "corrupt_out.webp"
        self.assertFalse(transcode_image(corrupt_src, dest))
        self.assertFalse(dest.exists())
        # Check no dangling .tmp files
        tmp_files = list(self.base_path.glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0)

    # --- Video Transcoding Tests with FFmpeg & Mocking ---

    @patch("subprocess.run")
    def test_transcode_video_successful_execution(self, mock_run):
        # Simulate successful FFmpeg run creating temp file
        def fake_ffmpeg(cmd, **kwargs):
            self.assertTrue("ffmpeg" in cmd[0])
            out_file = Path(cmd[-1])
            out_file.write_bytes(b"FAKE_MP4_CONTENT")
            result = MagicMock()
            result.returncode = 0
            return result

        mock_run.side_effect = fake_ffmpeg

        src = self.base_path / "sample.mkv"
        src.touch()
        dest = self.base_path / "output.mp4"

        self.assertTrue(transcode_video(src, dest))
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_bytes(), b"FAKE_MP4_CONTENT")

    @patch("subprocess.run")
    def test_transcode_video_error_cleans_up_temp(self, mock_run):
        def fake_ffmpeg_error(cmd, **kwargs):
            out_file = Path(cmd[-1])
            out_file.write_bytes(b"PARTIAL_BROKEN_DATA")
            result = MagicMock()
            result.returncode = 1
            result.stderr = "Invalid data found when processing input"
            return result

        mock_run.side_effect = fake_ffmpeg_error

        src = self.base_path / "broken.mkv"
        src.touch()
        dest = self.base_path / "broken_out.mp4"

        self.assertFalse(transcode_video(src, dest))
        self.assertFalse(dest.exists())
        tmp_files = list(self.base_path.glob("*.tmp.mp4"))
        self.assertEqual(len(tmp_files), 0)

    # --- transcode_media_if_needed Logic & Caching Tests ---

    def test_transcode_media_if_needed_standard_formats_skipped(self):
        standard_extensions = [".jpg", ".png", ".gif", ".webp", ".mp4", ".webm", ".mov"]
        for ext in standard_extensions:
            p = self.base_path / f"test{ext}"
            p.touch()
            self.assertIsNone(transcode_media_if_needed(p))

    def test_transcode_media_if_needed_unsupported_formats_skipped(self):
        unsupported = [".txt", ".zip", ".tar.gz", ".csv", ".exe", ".pdf"]
        for ext in unsupported:
            p = self.base_path / f"test{ext}"
            p.touch()
            self.assertIsNone(transcode_media_if_needed(p))

    def test_transcode_media_if_needed_reuses_existing_transcode(self):
        # Place an original file in ORIGINAL_DIR
        settings.ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
        settings.TRANSCODED_DIR.mkdir(parents=True, exist_ok=True)
        
        orig_file = settings.ORIGINAL_DIR / "cached_test.heic"
        orig_file.touch()

        expected_transcoded = settings.TRANSCODED_DIR / "cached_test.webp"
        expected_transcoded.write_bytes(b"ALREADY_TRANSCODED_WEBP_DATA")

        result = transcode_media_if_needed(orig_file)
        self.assertEqual(result, expected_transcoded)

        # Clean up test files from settings dirs
        orig_file.unlink(missing_ok=True)
        expected_transcoded.unlink(missing_ok=True)

    # --- Database Model & Schema Tests ---

    def test_media_model_and_schema_transcoded_path_field(self):
        from datetime import datetime, timezone
        media_inst = Media(
            id=1,
            filename="video.mkv",
            path="media/original/video.mkv",
            transcoded_path="media/transcoded/video.mp4",
            thumbnail_path="media/thumbnails/video.jpg",
            hash="abc123hash",
            file_type=FileTypeEnum.video,
            mime_type="video/x-matroska",
            file_size=1024000,
            width=1920,
            height=1080,
            duration=12.5,
            rating=RatingEnum.safe,
            uploaded_at=datetime.now(timezone.utc),
            is_shared=False,
        )
        self.assertEqual(media_inst.transcoded_path, "media/transcoded/video.mp4")

        # Test Pydantic serialization
        schema_obj = MediaResponse.model_validate(media_inst)
        self.assertEqual(schema_obj.transcoded_path, "media/transcoded/video.mp4")

    # --- Integration with process_media_file ---

    def test_process_media_file_integrates_transcode(self):
        # Create an image that requires transcoding
        settings.ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
        orig_heic = settings.ORIGINAL_DIR / "photo_process.heic"
        with Image.new("RGB", (320, 240), color=(100, 150, 200)) as img:
            img.save(orig_heic, "PNG")

        meta = process_media_file(orig_heic)
        self.assertEqual(meta["file_type"], FileTypeEnum.image)
        self.assertEqual(meta["width"], 320)
        self.assertEqual(meta["height"], 240)
        self.assertIsNotNone(meta["transcoded_path"])
        self.assertTrue(meta["transcoded_path"].endswith(".webp"))

        # Clean up
        orig_heic.unlink(missing_ok=True)
        trans_out = settings.BASE_DIR / meta["transcoded_path"]
        trans_out.unlink(missing_ok=True)

if __name__ == "__main__":
    unittest.main()
