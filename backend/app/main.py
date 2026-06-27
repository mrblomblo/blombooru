import asyncio
import json
import subprocess
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth_middleware import AuthMiddleware
from .config import APP_VERSION, settings
from .database import get_db, init_db, init_engine
from .models import Media, Album
from .routes import (admin, ai_tagger, albums, booru_config, booru_import,
                     danbooru, media, search, sharing, system, tag_implications,
                     tags, instance_info, url_import)
from .translations import language_registry, translation_helper
from .utils.logger import logger

def get_cache_buster():
    """Get the current git commit hash to use as a cache buster, fallback to APP_VERSION"""
    try:
        # Get short git hash
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to app version if git is not available
        return APP_VERSION

class DynamicCacheBuster:
    """Dynamic cache buster that returns a random UUID in debug mode"""
    def __init__(self, static_val):
        self.static_val = static_val
        
    def __str__(self):
        if settings.DEBUG:
            return str(uuid.uuid4())
        return self.static_val
        
    def __repr__(self):
        return str(self)

CACHE_BUSTER = DynamicCacheBuster(get_cache_buster())

from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import MutableHeaders
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send, Message

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler (startup and shutdown)"""
    cleanup_task = None
    dead_cache_task = None
    # Startup
    if settings.DEBUG:
        logger.warning("DEBUG MODE ENABLED - DO NOT USE IN PRODUCTION")
    if not settings.IS_FIRST_RUN:
        try:
            init_engine()
            init_db()

            # Clean up any leftover chunks from abandoned uploads
            from .routes.media import cleanup_archive_chunks, cleanup_media_chunks
            cleanup_archive_chunks()
            cleanup_media_chunks()

            # Start periodic cleanup task for abandoned uploads
            async def periodic_upload_chunks_cleanup():
                while True:
                    await asyncio.sleep(900)  # Every 15 minutes
                    try:
                        cleanup_archive_chunks(max_age_seconds=3600)
                        cleanup_media_chunks(max_age_seconds=3600)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Upload chunks cleanup error: {e}")

            cleanup_task = asyncio.create_task(periodic_upload_chunks_cleanup())

            # Start periodic dead-cache cleanup task
            async def periodic_dead_cache_cleanup():
                from .database import SessionLocal
                from .utils.media_helpers import cleanup_dead_media_cache
                while True:
                    await asyncio.sleep(6 * 3600)  # Every 6 hours
                    try:
                        if SessionLocal is None:
                            continue
                        db = SessionLocal()
                        try:
                            cleanup_dead_media_cache(db)
                        finally:
                            db.close()
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Dead cache cleanup error: {e}")

            dead_cache_task = asyncio.create_task(periodic_dead_cache_cleanup())

            logger.info("Blombooru started successfully")
        except Exception as e:
            logger.error(f"Error during startup: {e}")
    else:
        logger.info("First run detected - please complete onboarding")

    yield

    # Shutdown
    if cleanup_task:
        cleanup_task.cancel()
    if dead_cache_task:
        dead_cache_task.cancel()
    try:
        from .routes.ai_tagger import shutdown_tagger_resources
        shutdown_tagger_resources()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

class SecurityHeadersMiddleware:
    """Pure ASGI middleware for security headers.

    Directly patches the http.response.start message, avoiding extra
    memory-stream overhead on large file transfers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-Content-Type-Options", "nosniff")
                headers.append("X-Frame-Options", "DENY")
                headers.append("X-XSS-Protection", "1; mode=block")
            await send(message)

        await self.app(scope, receive, send_with_headers)

class SelectiveGZipMiddleware:
    """GZip middleware that skips binary media content types."""

    _SKIP_PREFIXES = ("video/", "image/", "audio/", "application/octet-stream")

    def __init__(self, app: ASGIApp, minimum_size: int = 1000) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        decided = False
        use_gzip = True

        async def inspect_send(message: Message) -> None:
            nonlocal decided, use_gzip
            if message["type"] == "http.response.start" and not decided:
                decided = True
                headers = dict(
                    (k.decode("latin-1").lower(), v.decode("latin-1"))
                    for k, v in message.get("headers", [])
                )
                ct = headers.get("content-type", "")
                if any(ct.startswith(p) for p in self._SKIP_PREFIXES):
                    use_gzip = False
            await send(message)

        # Media file endpoints always serve binary content.
        path = scope.get("path", "")
        if (
            path.startswith("/api/media/") and path.endswith("/file")
            or path.startswith("/api/media/") and path.endswith("/thumbnail")
            or path.startswith("/api/shared/") and path.endswith("/file")
            or path.startswith("/api/shared/") and path.endswith("/thumbnail")
        ):
            # Skip gzip on known binary media endpoints
            await self.app(scope, receive, send)
        else:
            await self.gzip(scope, receive, send)

app = FastAPI(title="Blombooru", version=APP_VERSION, lifespan=lifespan)
app.add_middleware(SelectiveGZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "app_name": settings.APP_NAME
        }, status_code=404)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

static_path = Path(__file__).parent.parent.parent / "frontend" / "static"
templates_path = Path(__file__).parent.parent.parent / "frontend" / "templates"

app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

_custom_themes_dir = settings.DATA_DIR / "custom_themes"
_custom_themes_dir.mkdir(parents=True, exist_ok=True)
app.mount("/data/themes", StaticFiles(directory=str(_custom_themes_dir)), name="custom_themes")

templates = Jinja2Templates(directory=str(templates_path))

templates.env.globals['app_version'] = APP_VERSION
templates.env.globals['cache_buster'] = CACHE_BUSTER
templates.env.globals['get_current_year'] = lambda: datetime.now().year
templates.env.globals['t'] = lambda key, **kwargs: translation_helper.get(key, settings.CURRENT_LANGUAGE, **kwargs)
templates.env.globals['get_translations_json'] = lambda: json.dumps(
    translation_helper.get_translations(settings.CURRENT_LANGUAGE)
)
templates.env.globals['current_language'] = lambda: settings.CURRENT_LANGUAGE
templates.env.globals['available_languages'] = lambda: [lang.to_dict() for lang in language_registry.get_all_languages()]
templates.env.globals['custom_background'] = lambda: settings.CUSTOM_BACKGROUND
templates.env.globals['require_auth'] = lambda: settings.REQUIRE_AUTH

def _is_authenticated_admin(request) -> bool:
    """Verify that the request has a valid admin_token JWT. Used by templates to show/hide
    admin-only UI elements. Does NOT rely on the client-controlled admin_mode cookie alone."""
    from .auth import get_current_user
    from .database import SessionLocal
    admin_token = request.cookies.get("admin_token")
    if not admin_token:
        return False
    if SessionLocal is None:
        return False
    db = SessionLocal()
    try:
        user = get_current_user(token=admin_token, admin_token=admin_token, db=db)
        return user is not None
    except Exception:
        return False
    finally:
        db.close()

templates.env.globals['is_admin'] = _is_authenticated_admin

app.include_router(admin.router)
app.include_router(instance_info.router)
app.include_router(media.router)
app.include_router(tags.router)
app.include_router(search.router)
app.include_router(sharing.router)
app.include_router(albums.router)
app.include_router(ai_tagger.router)
app.include_router(danbooru.router)
app.include_router(system.router)
app.include_router(booru_import.router)
app.include_router(url_import.router)
app.include_router(booru_config.router)
app.include_router(tag_implications.router)

def _get_theme_for_context(is_admin: bool = False):
    """Return the theme dict to inject into template context. Uses the theme's backup theme in the Admin Panel."""
    from .themes import theme_registry
    from .custom_themes import get_backup_theme_for

    theme = theme_registry.get_theme(settings.CURRENT_THEME)
    if theme is None:
        theme = theme_registry.get_theme("default_dark")
    if theme is None:
        return None

    if is_admin and theme.is_custom:
        backup = get_backup_theme_for(theme.id)
        if backup:
            return backup.to_dict()

    return theme.to_dict()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page"""
    if settings.IS_FIRST_RUN:
        return templates.TemplateResponse("onboarding.html", {
            "request": request,
            "app_name": settings.APP_NAME,
            "settings": settings
        })
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "default_sort": settings.get_default_sort(),
        "default_order": settings.get_default_order(),
        "popular_tags_mode": settings.get_popular_tags_mode(),
        "popular_tags_limit": settings.get_popular_tags_limit(),
        "sidebar_filter_mode": settings.SIDEBAR_FILTER_MODE,
        "sidebar_custom_buttons": settings.SIDEBAR_CUSTOM_BUTTONS
    })

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    """Admin panel - ALWAYS requires authentication regardless of REQUIRE_AUTH setting."""
    from .auth import get_current_user
    from .database import SessionLocal
    from urllib.parse import quote

    admin_token = request.cookies.get("admin_token")
    authenticated = False
    if admin_token and SessionLocal is not None:
        db = SessionLocal()
        try:
            user = get_current_user(token=admin_token, admin_token=admin_token, db=db)
            if user is not None:
                authenticated = True
        except Exception:
            pass
        finally:
            db.close()

    if not authenticated:
        return_url = quote("/admin")
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/login?return={return_url}", status_code=302)

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "current_theme": _get_theme_for_context(is_admin=True),
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return_url = request.query_params.get("return", "/")
    return templates.TemplateResponse("login.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "return_url": return_url,
        "is_login_page": True
    })

@app.get("/media/{media_id}", response_class=HTMLResponse)
async def media_page(request: Request, media_id: int, db: Session = Depends(get_db)):
    """Media detail page"""
    media_item = db.query(Media).filter(Media.id == media_id).first()
    if media_item is None:
        raise StarletteHTTPException(status_code=404, detail="Media not found")
        
    return templates.TemplateResponse("media.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "media_id": media_id,
        "media": media_item,
        "external_share_url": settings.EXTERNAL_SHARE_URL
    })

@app.get("/shared/{share_uuid}", response_class=HTMLResponse)
async def shared_page(request: Request, share_uuid: str, db: Session = Depends(get_db)):
    """Shared content page"""
    # Fetch media for Open Graph tags
    media = db.query(Media).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    context = {
        "request": request,
        "app_name": settings.APP_NAME,
        "share_uuid": share_uuid,
        "is_shared_page": True
    }
    
    if media:
        context["media"] = media
        # Construct absolute URL for OG image if possible, or relative
        if media.thumbnail_path:
            context["og_image"] = f"/api/shared/{share_uuid}/thumbnail"
        else:
            context["og_image"] = f"/api/shared/{share_uuid}/file"
            
    # Get current theme
    try:
        from .themes import theme_registry
        current_theme = theme_registry.get_theme(settings.CURRENT_THEME)
        if current_theme:
            context["current_theme"] = current_theme.to_dict()
    except Exception as e:
        logger.error(f"Error loading theme for shared page: {e}")
            
    # Handle language override
    target_lang = settings.CURRENT_LANGUAGE
    if media and media.share_language:
        target_lang = media.share_language
        
        # Override translation helper and language for this specific context
        context["t"] = lambda key, **kwargs: translation_helper.get(key, target_lang, **kwargs)
        context["current_language"] = lambda: target_lang
        
        # For valid HTML lang attribute
        context["html_lang"] = target_lang

    return templates.TemplateResponse("shared.html", context)

@app.get("/tags-gallery", response_class=HTMLResponse)
async def tags_overview_page(request: Request):
    return templates.TemplateResponse("tags_gallery.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "default_sort": settings.get_default_sort(),
        "default_order": settings.get_default_order(),
        "popular_tags_mode": settings.get_popular_tags_mode(),
        "popular_tags_limit": settings.get_popular_tags_limit(),
        "sidebar_filter_mode": settings.SIDEBAR_FILTER_MODE,
        "sidebar_custom_buttons": settings.SIDEBAR_CUSTOM_BUTTONS
    })

@app.get("/albums", response_class=HTMLResponse)
async def albums_page(request: Request):
    """Albums overview page"""
    return templates.TemplateResponse("albums.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "default_sort": settings.get_default_sort(),
        "default_order": settings.get_default_order(),
        "popular_tags_mode": settings.get_popular_tags_mode(),
        "popular_tags_limit": settings.get_popular_tags_limit(),
        "sidebar_filter_mode": settings.SIDEBAR_FILTER_MODE,
        "sidebar_custom_buttons": settings.SIDEBAR_CUSTOM_BUTTONS
    })

@app.get("/album/{album_id}", response_class=HTMLResponse)
async def album_detail_page(request: Request, album_id: int, db: Session = Depends(get_db)):
    """Album detail page"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if album is None:
        raise StarletteHTTPException(status_code=404, detail="Album not found")

    return templates.TemplateResponse("album.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "album_id": album_id,
        "default_sort": settings.get_default_sort(),
        "default_order": settings.get_default_order(),
        "popular_tags_mode": settings.get_popular_tags_mode(),
        "popular_tags_limit": settings.get_popular_tags_limit(),
        "sidebar_filter_mode": settings.SIDEBAR_FILTER_MODE,
        "sidebar_custom_buttons": settings.SIDEBAR_CUSTOM_BUTTONS
    })

@app.get("/theme-preview", response_class=HTMLResponse, include_in_schema=False)
async def theme_preview_page(request: Request):
    """Private theme preview page. Shows the current theme's palette.

    Requires authentication. The instance name is always shown as 'Blombooru',
    and the custom background is suppressed for privacy.
    """
    from .auth import get_current_user
    from .database import SessionLocal
    from urllib.parse import quote

    admin_token = request.cookies.get("admin_token")
    authenticated = False
    if admin_token and SessionLocal is not None:
        db = SessionLocal()
        try:
            user = get_current_user(token=admin_token, admin_token=admin_token, db=db)
            if user is not None:
                authenticated = True
        except Exception:
            pass
        finally:
            db.close()

    if not authenticated:
        return_url = quote("/theme-preview")
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/login?return={return_url}", status_code=302)

    from .themes import theme_registry
    from .custom_themes import get_backup_theme_for

    theme = theme_registry.get_theme(settings.CURRENT_THEME)
    if theme is None:
        theme = theme_registry.get_theme("default_dark")

    backup_theme = None
    if theme and theme.is_custom:
        backup_theme = get_backup_theme_for(theme.id)

    context = {
        "request": request,
        "app_name": "Blombooru",
        "current_theme": theme.to_dict() if theme else None,
        "backup_theme": backup_theme.to_dict() if backup_theme else None,
        "custom_background": lambda: {"enabled": False},
    }

    return templates.TemplateResponse("theme_preview.html", context)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(str(static_path / "favicon.ico"))

@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    from fastapi import Response
    content = (static_path / "sw.js").read_text()
    content = content.replace('__APP_VERSION__', APP_VERSION)
    content = content.replace('__DEBUG__', str(settings.DEBUG).lower())
    return Response(content=content, media_type="application/javascript")

@app.get("/manifest.json", response_class=JSONResponse)
async def manifest(request: Request):
    """Dynamic PWA manifest based on settings and theme"""
    from .themes import theme_registry
    from .custom_themes import get_backup_theme_for
    
    current_theme = theme_registry.get_theme(settings.CURRENT_THEME)

    # For custom themes use the backup theme's PWA colors, because the custom
    # CSS might not define --primary-color / --background reliably.
    if current_theme and current_theme.is_custom:
        backup = get_backup_theme_for(current_theme.id)
        if backup:
            current_theme = backup
    
    # Defaults if theme not found
    theme_color = "#3b82f6"
    background_color = "#0f172a"
    
    if current_theme:
        theme_color = current_theme.primary_color
        background_color = current_theme.background_color
        
    return {
        "name": settings.APP_NAME,
        "short_name": settings.APP_NAME,
        "description": "A modern, self-hosted, single-user image booru and media tagger",
        "id": "/",
        "scope": "/",
        "start_url": "/",
        "display": "standalone",
        "background_color": background_color,
        "theme_color": theme_color,
        "orientation": "any",
        "icons": [
            {
                "src": f"/static/images/pwa-icon.png?v={CACHE_BUSTER}",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": f"/static/images/pwa-icon-192.png?v={CACHE_BUSTER}",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    }
