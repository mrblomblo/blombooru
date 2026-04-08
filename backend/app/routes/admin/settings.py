from fastapi import APIRouter, Depends, HTTPException

from ...auth import get_current_admin_user, require_admin_mode
from ...config import settings
from ...models import User
from ...schemas import SettingsUpdate
from ...themes import theme_registry
from ...utils.cache import invalidate_media_cache
from ...utils.logger import logger

router = APIRouter()

@router.get("/settings")
async def get_settings(current_user: User = Depends(get_current_admin_user)):
    """Get current settings"""
    safe_settings = settings.settings.copy()
    if "database" in safe_settings:
        safe_settings["database"] = {**safe_settings["database"], "password": "***"}
    if "redis" in safe_settings:
        safe_settings["redis"] = {**safe_settings["redis"], "password": "***"}
    if "shared_tags" in safe_settings:
        safe_settings["shared_tags"] = {**safe_settings["shared_tags"], "password": "***"}
    safe_settings.pop("secret_key", None)
    return safe_settings

@router.post("/test-redis")
async def test_redis(data: dict, current_user: User = Depends(require_admin_mode)):
    """Test Redis connection"""
    import redis
    try:
        host = data.get('host', 'redis')
        port = data.get('port', 6379)
        db = data.get('db', 0)
        password = data.get('password')
        if password == "***":
            password = settings.REDIS_PASSWORD

        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
            socket_connect_timeout=2
        )
        client.ping()
        return {"success": True, "message_key": "notifications.admin.redis_connection_successful"}
    except Exception as e:
        return {"success": False, "message_key": "notifications.admin.redis_connection_failed", "error": str(e)}

@router.patch("/settings")
async def update_settings(
    updates: SettingsUpdate,
    current_user: User = Depends(require_admin_mode),
):
    """Update settings"""
    update_dict = updates.dict(exclude_unset=True)
    
    if "redis" in update_dict and update_dict["redis"].get("password") == "***":
        update_dict["redis"]["password"] = settings.REDIS_PASSWORD
    
    if "shared_tags" in update_dict and update_dict["shared_tags"].get("password") == "***":
        update_dict["shared_tags"]["password"] = settings.SHARED_TAG_DB_PASSWORD

    settings.save_settings(update_dict)
    
    from ...redis_client import redis_cache
    if "redis" in update_dict:
        redis_cache._enabled = settings.REDIS_ENABLED
        redis_cache._client = None
    
    if "shared_tags" in update_dict:
        from ...database import init_shared_db, reconnect_shared_db
        reconnect_shared_db()
        if settings.SHARED_TAGS_ENABLED:
            init_shared_db()
        
    invalidate_media_cache()
        
    return {"message_key": "notifications.admin.settings_updated"}

@router.get("/themes")
async def get_themes():
    """Get all available themes"""
    themes = theme_registry.get_all_themes()
    return {
        "themes": [theme.to_dict() for theme in themes],
        "current_theme": settings.CURRENT_THEME
    }

@router.get("/current-theme")
async def get_current_theme():
    """Get current theme (public endpoint)"""
    theme = theme_registry.get_theme(settings.CURRENT_THEME)
    if theme:
        return theme.to_dict()
    return theme_registry.get_theme("default_dark").to_dict()

@router.get("/languages")
async def get_languages():
    """Get all available languages"""
    from ...translations import language_registry
    languages = language_registry.get_all_languages()
    return {
        "languages": [lang.to_dict() for lang in languages],
        "current_language": settings.CURRENT_LANGUAGE
    }

@router.get("/translations")
async def get_translations(lang: str = None):
    """Get translation strings for the current or specified language"""
    from ...translations import translation_helper
    target_lang = lang or settings.CURRENT_LANGUAGE
    return translation_helper.get_translations(target_lang)
