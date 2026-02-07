from fastapi import FastAPI, Request, Depends
from sqlalchemy.orm import Session
from .models import Media
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pathlib import Path
from .config import settings
from .database import get_db, init_db, init_engine
from .routes import admin, media, tags, search, sharing, albums, ai_tagger, danbooru, system
from .auth_middleware import AuthMiddleware
from .translations import translation_helper, language_registry
from datetime import datetime

APP_VERSION = "1.33.12"

app = FastAPI(title="Blombooru", version=APP_VERSION)
app.add_middleware(AuthMiddleware)
static_path = Path(__file__).parent.parent.parent / "frontend" / "static"
templates_path = Path(__file__).parent.parent.parent / "frontend" / "templates"

app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
templates = Jinja2Templates(directory=str(templates_path))

templates.env.globals['app_version'] = APP_VERSION
templates.env.globals['get_current_year'] = lambda: datetime.now().year
templates.env.globals['t'] = lambda key, **kwargs: translation_helper.get(key, settings.CURRENT_LANGUAGE, **kwargs)
templates.env.globals['current_language'] = lambda: settings.CURRENT_LANGUAGE
templates.env.globals['available_languages'] = lambda: [lang.to_dict() for lang in language_registry.get_all_languages()]
templates.env.globals['is_admin'] = lambda request: request.cookies.get("admin_mode") == "true"
app.include_router(admin.router)
app.include_router(media.router)
app.include_router(tags.router)
app.include_router(search.router)
app.include_router(sharing.router)
app.include_router(albums.router)
app.include_router(ai_tagger.router)
app.include_router(danbooru.router)
app.include_router(system.router)

@app.on_event("startup")
async def startup_event():
    """Run on startup"""
    if not settings.IS_FIRST_RUN:
        try:
            init_engine()
            init_db()
                
            print("Blombooru started successfully")
        except Exception as e:
            print(f"Error during startup: {e}")
    else:
        print("First run detected - please complete onboarding")

@app.on_event("shutdown")
async def shutdown_event():
    """Run on shutdown"""
    try:
        from .routes.ai_tagger import shutdown_tagger_resources
        shutdown_tagger_resources()
    except Exception as e:
        print(f"Error during shutdown: {e}")

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
        "sidebar_filter_mode": settings.SIDEBAR_FILTER_MODE,
        "sidebar_custom_buttons": settings.SIDEBAR_CUSTOM_BUTTONS
    })

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    """Admin panel"""
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "app_name": settings.APP_NAME
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return_url = request.query_params.get("return", "/")
    return templates.TemplateResponse("login.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "return_url": return_url
    })

@app.get("/media/{media_id}", response_class=HTMLResponse)
async def media_page(request: Request, media_id: int, db: Session = Depends(get_db)):
    """Media detail page"""
    media_item = db.query(Media).filter(Media.id == media_id).first()
    
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
        "share_uuid": share_uuid
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
        print(f"Error loading theme for shared page: {e}")
            
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

@app.get("/albums", response_class=HTMLResponse)
async def albums_page(request: Request):
    """Albums overview page"""
    return templates.TemplateResponse("albums.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "default_sort": settings.get_default_sort(),
        "default_order": settings.get_default_order(),
        "sidebar_filter_mode": settings.SIDEBAR_FILTER_MODE,
        "sidebar_custom_buttons": settings.SIDEBAR_CUSTOM_BUTTONS
    })

@app.get("/album/{album_id}", response_class=HTMLResponse)
async def album_detail_page(request: Request, album_id: int):
    """Album detail page"""
    return templates.TemplateResponse("album.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "album_id": album_id,
        "default_sort": settings.get_default_sort(),
        "default_order": settings.get_default_order(),
        "sidebar_filter_mode": settings.SIDEBAR_FILTER_MODE,
        "sidebar_custom_buttons": settings.SIDEBAR_CUSTOM_BUTTONS
    })

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(str(static_path / "favicon.ico"))

@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(str(static_path / "sw.js"), media_type="application/javascript")

@app.get("/manifest.json", response_class=JSONResponse)
async def manifest(request: Request):
    """Dynamic PWA manifest based on settings and theme"""
    from .themes import theme_registry
    
    current_theme = theme_registry.get_theme(settings.CURRENT_THEME)
    
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
                "src": f"/static/images/pwa-icon.png?v={APP_VERSION}",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": f"/static/images/pwa-icon-192.png?v={APP_VERSION}",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    }
