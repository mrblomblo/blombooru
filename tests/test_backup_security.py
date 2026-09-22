import io
import json
import unittest
import zipfile

from backend.app.models import Media
from backend.app.utils.backup import _safe_extract_media_file, import_full_backup
from tests.test_base import BackupTestBase

class TestBackupSecurity(BackupTestBase):
    def test_zip_slip_security_protection(self):
        """Test that malicious backup archives with directory traversal paths are rejected."""
        # 1. Direct unit test of _safe_extract_media_file rejecting traversal paths
        zip_buffer_direct = io.BytesIO()
        with zipfile.ZipFile(zip_buffer_direct, 'w') as zf:
            zf.writestr("media/../../../../etc/passwd", b"malicious content")
        zip_buffer_direct.seek(0)
        with zipfile.ZipFile(zip_buffer_direct, 'r') as zf:
            with self.assertRaises(ValueError) as ctx:
                _safe_extract_media_file(zf, "media/../../../../etc/passwd", "../../../../etc/passwd")
            self.assertIn("Illegal path", str(ctx.exception))

        # 2. Integration test: import_full_backup ignores malicious entries without writing outside ORIGINAL_DIR
        escaped_file = self.tmp_path / "evil_escaped.txt"
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr("tags.csv", "safe_tag,0,0,\n")
            meta = {
                "type": "full_backup",
                "media": [
                    {
                        "filename": "hacked.jpg",
                        "hash": "badhash123",
                        "file_type": "image",
                        "mime_type": "image/jpeg",
                        "archive_path": "media/../../evil_escaped.txt"
                    }
                ]
            }
            zf.writestr("backup.json", json.dumps(meta))
            zf.writestr("media/../../evil_escaped.txt", b"evil content")

        zip_buffer.seek(0)
        result = import_full_backup(zip_buffer, self.db)
        self.assertEqual(result["message"], "Import completed successfully")
        self.assertFalse(escaped_file.exists())
        self.assertIsNone(self.db.query(Media).filter(Media.hash == "badhash123").first())

if __name__ == "__main__":
    unittest.main()
