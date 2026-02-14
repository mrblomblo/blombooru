import json
import os
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        self.BASE_DIR = Path(__file__).resolve().parent.parent.parent
        self.MEDIA_DIR = self.BASE_DIR / "media"
        self.ORIGINAL_DIR = self.MEDIA_DIR / "original"
        self.THUMBNAIL_DIR = self.MEDIA_DIR / "thumbnails"
        self.CACHE_DIR = self.MEDIA_DIR / "cache"
        self.DATA_DIR = self.BASE_DIR / "data"
        self.SETTINGS_FILE = self.DATA_DIR / "settings.json"
        
        self.ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
        self.THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        self.file_settings = self._load_file_settings()
        self.settings = self._get_default_settings()
        self.settings.update(self.file_settings)
        
    @property
    def DEBUG(self) -> bool:
        return os.getenv("BLOMBOORU_DEBUG", "false").lower() == "true"
    
    def _load_file_settings(self) -> dict:
        if self.SETTINGS_FILE.exists():
            with open(self.SETTINGS_FILE, 'r') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}
        
    def _get_default_settings(self) -> dict:
        return {
            "app_name": "Blombooru",
            "first_run": True,
            "database": {
                "host": "db",
                "port": 5432,
                "name": "blombooru",
                "user": "postgres",
                "password": ""
            },
            "redis": {
                "host": "redis",
                "port": 6379,
                "db": 0,
                "password": "",
                "enabled": False
            },
            "shared_tags": {
                "enabled": False,
                "host": "shared-tag-db",
                "port": 5432,
                "name": "shared_tags",
                "user": "postgres",
                "password": ""
            },
            "items_per_page": 64,
            "default_sort": "uploaded_at",
            "default_order": "desc",
            "sidebar_filter_mode": "rating",
            "sidebar_custom_buttons": [],
            "secret_key": os.urandom(32).hex()
        }
    
    def get_items_per_page(self) -> int:
        """Get items per page setting"""
        return self.settings.get("items_per_page", 64)
    
    def get_default_sort(self) -> str:
        """Get default sort setting"""
        return self.settings.get("default_sort", "uploaded_at")
        
    def get_default_order(self) -> str:
        """Get default order setting"""
        return self.settings.get("default_order", "desc")
    
    def save_settings(self, settings: dict):
        self.settings.update(settings)
        self.file_settings.update(settings)
        with open(self.SETTINGS_FILE, 'w') as f:
            json.dump(self.settings, f, indent=2)
    
    @property
    def DB_USER(self) -> str:
        return self.file_settings.get("database", {}).get('user') or os.getenv("POSTGRES_USER") or self.settings.get("database", {}).get('user', 'postgres')

    @property
    def DB_PASSWORD(self) -> str:
        return self.file_settings.get("database", {}).get('password') or os.getenv("POSTGRES_PASSWORD") or self.settings.get("database", {}).get('password', '')

    @property
    def DB_HOST(self) -> str:
        return self.file_settings.get("database", {}).get('host') or os.getenv("POSTGRES_HOST") or self.settings.get("database", {}).get('host', 'localhost')

    @property
    def DB_PORT(self) -> int:
        return int(self.file_settings.get("database", {}).get('port') or os.getenv("POSTGRES_PORT") or self.settings.get("database", {}).get('port', 5432))

    @property
    def DB_NAME(self) -> str:
        return self.file_settings.get("database", {}).get('name') or os.getenv("POSTGRES_DB") or self.settings.get("database", {}).get('name', 'blombooru')

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def REDIS_HOST(self) -> str:
        val = self.file_settings.get("redis", {}).get("host")
        if val is not None:
            return val
        return os.getenv("REDIS_HOST", self.settings.get("redis", {}).get("host", "localhost"))
    
    @property
    def REDIS_PORT(self) -> int:
        val = self.file_settings.get("redis", {}).get("port")
        if val is not None:
            return int(val)
        return int(os.getenv("REDIS_PORT", self.settings.get("redis", {}).get("port", 6379)))
    
    @property
    def REDIS_DB(self) -> int:
        val = self.file_settings.get("redis", {}).get("db")
        if val is not None:
            return int(val)
        return int(os.getenv("REDIS_DB", self.settings.get("redis", {}).get("db", 0)))
    
    @property
    def REDIS_PASSWORD(self) -> Optional[str]:
        val = self.file_settings.get("redis", {}).get("password")
        if val is not None:
            return val
        return os.getenv("REDIS_PASSWORD", self.settings.get("redis", {}).get("password"))
    
    @property
    def REDIS_ENABLED(self) -> bool:
        file_enabled = self.file_settings.get("redis", {}).get("enabled")
        if file_enabled is not None:
            if isinstance(file_enabled, bool):
                return file_enabled
            return str(file_enabled).lower() in ("true", "1", "yes")
            
        env_enabled = os.getenv("REDIS_ENABLED")
        if env_enabled is not None:
            return env_enabled.lower() in ("true", "1", "yes")
            
        return self.settings.get("redis", {}).get("enabled", False)
    
    @property
    def SECRET_KEY(self) -> str:
        return self.settings["secret_key"]
    
    @property
    def APP_NAME(self) -> str:
        val = self.file_settings.get("app_name")
        if val is not None:
            return val
        return os.getenv("APP_NAME", self.settings.get("app_name", "Blombooru"))
    
    @property
    def CURRENT_THEME(self) -> str:
        return self.settings.get("theme", "default_dark")
    
    @property
    def CURRENT_LANGUAGE(self) -> str:
        return self.settings.get("language", "en")
    
    @property
    def IS_FIRST_RUN(self) -> bool:
        return self.settings.get("first_run", True)
        
    @property
    def EXTERNAL_SHARE_URL(self) -> Optional[str]:
        return self.settings.get("external_share_url")
    
    @property
    def REQUIRE_AUTH(self) -> bool:
        return self.settings.get("require_auth", False)
    
    @property
    def SIDEBAR_FILTER_MODE(self) -> str:
        """Get sidebar filter mode: 'rating', 'custom', or 'off'"""
        return self.settings.get("sidebar_filter_mode", "rating")
    
    @property
    def SIDEBAR_CUSTOM_BUTTONS(self) -> List[dict]:
        """Get custom sidebar buttons: list of {title, tags}"""
        return self.settings.get("sidebar_custom_buttons", [])
    
    @property
    def SHARED_TAGS_ENABLED(self) -> bool:
        """Check if shared tag database is enabled"""
        file_enabled = self.file_settings.get("shared_tags", {}).get("enabled")
        if file_enabled is not None:
            if isinstance(file_enabled, bool):
                return file_enabled
            return str(file_enabled).lower() in ("true", "1", "yes")
        
        env_enabled = os.getenv("SHARED_TAGS_ENABLED")
        if env_enabled is not None:
            return env_enabled.lower() in ("true", "1", "yes")
        
        return self.settings.get("shared_tags", {}).get("enabled", False)
    
    @property
    def SHARED_TAG_DB_HOST(self) -> str:
        return self.file_settings.get("shared_tags", {}).get("host") or os.getenv("SHARED_TAG_DB_HOST") or self.settings.get("shared_tags", {}).get("host", "localhost")
    
    @property
    def SHARED_TAG_DB_PORT(self) -> int:
        return int(self.file_settings.get("shared_tags", {}).get("port") or os.getenv("SHARED_TAG_DB_PORT") or self.settings.get("shared_tags", {}).get("port", 5432))
    
    @property
    def SHARED_TAG_DB_NAME(self) -> str:
        return self.file_settings.get("shared_tags", {}).get("name") or os.getenv("SHARED_TAG_DB_NAME") or self.settings.get("shared_tags", {}).get("name", "shared_tags")
    
    @property
    def SHARED_TAG_DB_USER(self) -> str:
        return self.file_settings.get("shared_tags", {}).get("user") or os.getenv("SHARED_TAG_DB_USER") or self.settings.get("shared_tags", {}).get("user", "postgres")
    
    @property
    def SHARED_TAG_DB_PASSWORD(self) -> str:
        return self.file_settings.get("shared_tags", {}).get("password") or os.getenv("SHARED_TAG_DB_PASSWORD") or self.settings.get("shared_tags", {}).get("password", "")
    
    @property
    def SHARED_TAG_DATABASE_URL(self) -> str:
        """Get shared tag database connection URL"""
        return f"postgresql://{self.SHARED_TAG_DB_USER}:{self.SHARED_TAG_DB_PASSWORD}@{self.SHARED_TAG_DB_HOST}:{self.SHARED_TAG_DB_PORT}/{self.SHARED_TAG_DB_NAME}"

settings = Settings()
