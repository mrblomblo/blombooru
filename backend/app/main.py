from fastapi import FastAPI, Request, Depends
from sqlalchemy.orm import Session
from .models import Media
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pathlib import Path
from .config import settings
from .database import get_db, init_db, init_engine
from .routes import admin, media, tags, search, sharing, albums, ai_tagger
from datetime import datetime

app = FastAPI(title="Blombooru", version="1.20.1")

static_path = Path(__file__).parent.parent.parent / "frontend" / "static"
templates_path = Path(__file__).parent.parent.parent / "frontend" / "templates"

app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
templates = Jinja2Templates(directory=str(templates_path))

templates.env.globals['get_current_year'] = lambda: datetime.now().year

app.include_router(admin.router)
app.include_router(media.router)
app.include_router(tags.router)
app.include_router(search.router)
app.include_router(sharing.router)
app.include_router(albums.router)
app.include_router(ai_tagger.router)

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

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page"""
    if settings.IS_FIRST_RUN:
        return templates.TemplateResponse("onboarding.html", {
            "request": request,
            "app_name": settings.APP_NAME
        })
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "default_sort": settings.get_default_sort(),
        "default_order": settings.get_default_order()
    })

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    """Admin panel"""
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "app_name": settings.APP_NAME
    })

@app.get("/media/{media_id}", response_class=HTMLResponse)
async def media_page(request: Request, media_id: int):
    """Media detail page"""
    return templates.TemplateResponse("media.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "media_id": media_id
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
            
    return templates.TemplateResponse("shared.html", context)

@app.get("/albums", response_class=HTMLResponse)
async def albums_page(request: Request):
    """Albums overview page"""
    return templates.TemplateResponse("albums.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "default_sort": settings.get_default_sort(),
        "default_order": settings.get_default_order()
    })

@app.get("/album/{album_id}", response_class=HTMLResponse)
async def album_detail_page(request: Request, album_id: int):
    """Album detail page"""
    return templates.TemplateResponse("album.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "album_id": album_id,
        "default_sort": settings.get_default_sort(),
        "default_order": settings.get_default_order()
    })

