import io
import unittest
import zipfile

from backend.app.utils.backup import stream_zip_generator
from tests.test_base import BackupTestBase

class TestBackupStreaming(BackupTestBase):
    def test_stream_zip_generator_large_file(self):
        """Test that stream_zip_generator streams files continuously without range limits."""
        large_file = self.original_dir / "large_video.mp4"
        # 3MB test file (greater than 2MB initial chunk size)
        chunk_pattern = b"A" * 1024 * 1024
        large_file.write_bytes(chunk_pattern * 3)

        def files_gen():
            yield ("media/large_video.mp4", large_file)

        zip_gen = stream_zip_generator(files_gen())
        accumulated = io.BytesIO()
        for chunk in zip_gen:
            accumulated.write(chunk)

        accumulated.seek(0)
        with zipfile.ZipFile(accumulated, 'r') as zf:
            self.assertIn("media/large_video.mp4", zf.namelist())
            extracted_data = zf.read("media/large_video.mp4")
            self.assertEqual(len(extracted_data), 3 * 1024 * 1024)

if __name__ == "__main__":
    unittest.main()
