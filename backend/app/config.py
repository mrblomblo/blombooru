import json
import os
from pathlib import Path
from typing import Optional

class Settings:
    def __init__(self):
        self.BASE_DIR = Path(__file__).resolve().parent.parent.parent
        self.MEDIA_DIR = self.BASE_DIR / "media"
        self.ORIGINAL_DIR = self.MEDIA_DIR / "original"
        self.THUMBNAIL_DIR = self.MEDIA_DIR / "thumbnails"
        self.DATA_DIR = self.BASE_DIR / "data"
        self.SETTINGS_FILE = self.DATA_DIR / "settings.json"
        
        # Create directories
        self.ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
        self.THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Load settings
        self.settings = self.load_settings()
        
    def load_settings(self) -> dict:
        if self.SETTINGS_FILE.exists():
            with open(self.SETTINGS_FILE, 'r') as f:
                return json.load(f)
        return {
            "app_name": "Blombooru",
            "first_run": True,
            "database": {
                "host": "localhost",
                "port": 5432,
                "name": "blombooru",
                "user": "postgres",
                "password": ""
            },
            "default_rating_filter": "explicit",
            "items_per_page": 30,
            "secret_key": os.urandom(32).hex()
        }
    
    def save_settings(self, settings: dict):
        self.settings.update(settings)
        with open(self.SETTINGS_FILE, 'w') as f:
            json.dump(self.settings, f, indent=2)
    
    @property
    def DATABASE_URL(self) -> str:
        db = self.settings["database"]
        return f"postgresql://{db['user']}:{db['password']}@{db['host']}:{db['port']}/{db['name']}"
    
    @property
    def SECRET_KEY(self) -> str:
        return self.settings["secret_key"]
    
    @property
    def APP_NAME(self) -> str:
        return self.settings["app_name"]
    
    @property
    def IS_FIRST_RUN(self) -> bool:
        return self.settings.get("first_run", True)

settings = Settings()
