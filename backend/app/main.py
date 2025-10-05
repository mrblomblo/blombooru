from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from apscheduler.schedulers.background import BackgroundScheduler
from pathlib import Path

from .config import settings
from .database import get_db, init_db, init_engine
from .routes import admin, media, tags, albums, search, sharing
from .utils.file_scanner import scan_for_new_media

app = FastAPI(title="Blombooru", version="1.0.0")

# Mount static files
static_path = Path(__file__).parent.parent.parent / "frontend" / "static"
templates_path = Path(__file__).parent.parent.parent / "frontend" / "templates"

app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
templates = Jinja2Templates(directory=str(templates_path))

# Include routers
app.include_router(admin.router)
app.include_router(media.router)
app.include_router(tags.router)
app.include_router(albums.router)
app.include_router(search.router)
app.include_router(sharing.router)

# Scheduled tasks
def scheduled_media_scan():
    """Scan for new media every 6 hours"""
    if settings.IS_FIRST_RUN:
        return
        
    from .database import SessionLocal
    if SessionLocal is None:
        return
        
    db = SessionLocal()
    try:
        result = scan_for_new_media(db)
        print(f"Scheduled scan: {result['new_files']} new files found")
    except Exception as e:
        print(f"Error in scheduled scan: {e}")
    finally:
        db.close()

scheduler = BackgroundScheduler()

@app.on_event("startup")
async def startup_event():
    """Run on startup"""
    if not settings.IS_FIRST_RUN:
        try:
            # Initialize database engine
            init_engine()
            
            # Initialize database schema
            init_db()
            
            # Run initial media scan
            from .database import SessionLocal
            db = SessionLocal()
            try:
                scan_for_new_media(db)
            except Exception as e:
                print(f"Error in startup scan: {e}")
            finally:
                db.close()
            
            # Start scheduler
            scheduler.add_job(scheduled_media_scan, 'interval', hours=6)
            scheduler.start()
            print("Blombooru started successfully")
        except Exception as e:
            print(f"Error during startup: {e}")
    else:
        print("First run detected - please complete onboarding")

@app.on_event("shutdown")
async def shutdown_event():
    """Run on shutdown"""
    if scheduler.running:
        scheduler.shutdown()

# HTML Routes
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
        "app_name": settings.APP_NAME
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

@app.get("/albums", response_class=HTMLResponse)
async def albums_page(request: Request):
    """Albums page"""
    return templates.TemplateResponse("albums.html", {
        "request": request,
        "app_name": settings.APP_NAME
    })

@app.get("/albums/{album_id}", response_class=HTMLResponse)
async def album_page(request: Request, album_id: int):
    """Album detail page"""
    return templates.TemplateResponse("album.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "album_id": album_id
    })

@app.get("/shared/{share_uuid}", response_class=HTMLResponse)
async def shared_page(request: Request, share_uuid: str):
    """Shared content page"""
    return templates.TemplateResponse("shared.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "share_uuid": share_uuid
    })
