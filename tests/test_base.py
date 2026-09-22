import io
import shutil
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings
from backend.app.database import Base
from backend.app.models import (Album, BooruConfig, Media, Tag, TagAlias,
                                TagImplication, blombooru_album_hierarchy,
                                blombooru_album_media,
                                blombooru_implication_implied,
                                blombooru_implication_targets,
                                blombooru_media_tags)
from backend.app.redis_client import redis_cache

def make_dummy_jpeg() -> bytes:
    """Generates a minimal valid JPEG image bytes for tests."""
    buf = io.BytesIO()
    img = Image.new("RGB", (32, 32), color="red")
    img.save(buf, format="JPEG")
    return buf.getvalue()

class BlombooruTestSandboxMixin:
    """Provides temporary filesystem sandboxes, test database, settings and Redis isolation."""

    def setup_sandbox(self):
        self.temp_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.temp_dir)
        self.base_path = self.tmp_path

        db_file = self.tmp_path / "test.db"
        self.engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(bind=self.engine)
        self.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.SessionLocal = self.TestingSessionLocal
        self.db = self.TestingSessionLocal()

        self.media_dir = self.tmp_path / "media"
        self.original_dir = self.media_dir / "original"
        self.thumbnail_dir = self.media_dir / "thumbnails"
        self.transcoded_dir = self.media_dir / "transcoded"
        self.cache_dir = self.media_dir / "cache"
        self.chunks_dir = self.cache_dir / "media-chunks"
        self.data_dir = self.tmp_path / "data"
        self.custom_themes_dir = self.data_dir / "custom_themes"

        self.original_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        self.transcoded_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        self.custom_themes_dir.mkdir(parents=True, exist_ok=True)

        self.upload_sessions_dir = self.cache_dir / "upload-sessions"
        self.upload_sessions_dir.mkdir(parents=True, exist_ok=True)

        import backend.app.routes.uploads as uploads_module
        self.old_module_sessions_dir = uploads_module.UPLOAD_SESSIONS_DIR
        uploads_module.UPLOAD_SESSIONS_DIR = self.upload_sessions_dir

        self.old_base_dir = settings.BASE_DIR
        self.old_media_dir = settings.MEDIA_DIR
        self.old_original_dir = settings.ORIGINAL_DIR
        self.old_thumbnail_dir = settings.THUMBNAIL_DIR
        self.old_transcoded_dir = settings.TRANSCODED_DIR
        self.old_cache_dir = settings.CACHE_DIR
        self.old_data_dir = settings.DATA_DIR
        self.old_settings_file = settings.SETTINGS_FILE
        self.old_settings_dict = dict(settings.settings)
        self.old_file_settings_dict = dict(settings.file_settings)

        settings.BASE_DIR = self.tmp_path
        settings.MEDIA_DIR = self.media_dir
        settings.ORIGINAL_DIR = self.original_dir
        settings.THUMBNAIL_DIR = self.thumbnail_dir
        settings.TRANSCODED_DIR = self.transcoded_dir
        settings.CACHE_DIR = self.cache_dir
        settings.DATA_DIR = self.data_dir
        settings.SETTINGS_FILE = self.data_dir / "settings.json"
        settings.file_settings = {}
        settings.settings = settings._get_default_settings()

        self.old_redis_enabled = redis_cache._enabled
        self.old_redis_client = redis_cache._client
        redis_cache._enabled = False
        redis_cache._client = None

    def teardown_sandbox(self):
        if hasattr(self, "db") and self.db is not None:
            self.db.close()
        if hasattr(self, "engine") and self.engine is not None:
            self.engine.dispose()
        import backend.app.routes.uploads as uploads_module
        uploads_module.UPLOAD_SESSIONS_DIR = self.old_module_sessions_dir
        settings.BASE_DIR = self.old_base_dir
        settings.MEDIA_DIR = self.old_media_dir
        settings.ORIGINAL_DIR = self.old_original_dir
        settings.THUMBNAIL_DIR = self.old_thumbnail_dir
        settings.TRANSCODED_DIR = self.old_transcoded_dir
        settings.CACHE_DIR = self.old_cache_dir
        settings.DATA_DIR = self.old_data_dir
        settings.SETTINGS_FILE = self.old_settings_file
        settings.file_settings = self.old_file_settings_dict
        settings.settings = self.old_settings_dict
        redis_cache._enabled = self.old_redis_enabled
        redis_cache._client = self.old_redis_client
        if hasattr(self, "temp_dir") and self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def wipe_database(self):
        self.db.execute(blombooru_album_hierarchy.delete())
        self.db.execute(blombooru_album_media.delete())
        self.db.execute(blombooru_media_tags.delete())
        self.db.execute(blombooru_implication_targets.delete())
        self.db.execute(blombooru_implication_implied.delete())
        self.db.query(TagImplication).delete()
        self.db.query(BooruConfig).delete()
        self.db.query(Album).delete()
        self.db.query(Media).delete()
        self.db.query(TagAlias).delete()
        self.db.query(Tag).delete()
        self.db.commit()
        self.db.expunge_all()

class BackupTestBase(BlombooruTestSandboxMixin, unittest.TestCase):
    """Base test class providing temporary filesystem sandboxes, test database, and settings isolation."""

    def setUp(self):
        super().setUp()
        self.setup_sandbox()

    def tearDown(self):
        self.teardown_sandbox()
        super().tearDown()

class AsyncBackupTestBase(BlombooruTestSandboxMixin, unittest.IsolatedAsyncioTestCase):
    """Async base test class providing temporary filesystem sandboxes, test database, and settings isolation."""

    def setUp(self):
        super().setUp()
        self.setup_sandbox()

    def tearDown(self):
        self.teardown_sandbox()
        super().tearDown()
