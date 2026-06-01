from fastapi import APIRouter

from ..config import APP_VERSION, settings
from ..themes import theme_registry

router = APIRouter(prefix="/api", tags=["instance-info"])

@router.get("/instance-info")
async def get_instance_info():
    """Return harmless instance metadata (public, no auth required)."""
    from ..translations import language_registry
    theme = theme_registry.get_theme(settings.CURRENT_THEME)
    if not theme:
        theme = theme_registry.get_theme("default_dark")
    lang_id = settings.CURRENT_LANGUAGE
    lang = language_registry.get_language(lang_id)
    return {
        "app_name": settings.APP_NAME,
        "app_version": APP_VERSION,
        "auth_required": settings.REQUIRE_AUTH,
        "theme": theme.to_dict(),
        "language": {
            "id": lang_id,
            "name": lang.name if lang else lang_id,
            "native_name": lang.native_name if lang else lang_id,
        },
    }
