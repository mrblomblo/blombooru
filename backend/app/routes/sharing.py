import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy.orm import Session, joinedload

from ..config import settings
from ..database import get_db
from ..models import Media
from ..schemas import SharedMediaResponse
from ..utils.media_helpers import (create_stripped_media_cache,
                                   extract_media_metadata,
                                   get_media_cache_status, serve_media_file)
from ..utils.rate_limiter import shared_limiter

router = APIRouter(prefix="/api/shared", tags=["sharing"])

@router.get("/{share_uuid}")
async def get_shared_content(share_uuid: str, request: Request, db: Session = Depends(get_db)):
    """Get shared media"""
    shared_limiter.check(request)
    
    media = db.query(Media).options(joinedload(Media.tags)).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    if media:
        media_dict = SharedMediaResponse.model_validate(media).model_dump()
        media_dict['share_ai_metadata'] = media.share_ai_metadata
        
        return {
            "type": "media",
            "data": media_dict
        }

    raise HTTPException(status_code=404, detail="Shared content not found")

@router.get("/{share_uuid}/file")
async def get_shared_file(share_uuid: str, request: Request, db: Session = Depends(get_db)):
    """Serve shared media file with metadata stripped if AI metadata not shared"""
    shared_limiter.check(request)
    media = db.query(Media).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    if not media:
        raise HTTPException(status_code=404, detail="Shared media not found")
    
    file_path = settings.BASE_DIR / media.path
    strip_metadata = not media.share_ai_metadata
    
    return await serve_media_file(file_path, media.mime_type, strip_metadata=strip_metadata)

@router.get("/{share_uuid}/thumbnail")
async def get_shared_thumbnail(share_uuid: str, request: Request, db: Session = Depends(get_db)):
    """Serve shared media thumbnail"""
    shared_limiter.check(request)
    media = db.query(Media).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    if not media or not media.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    
    thumb_path = settings.BASE_DIR / media.thumbnail_path
    return await serve_media_file(thumb_path, "image/jpeg", "Thumbnail file not found")

@router.get("/{share_uuid}/metadata")
async def get_shared_metadata(share_uuid: str, request: Request, db: Session = Depends(get_db)):
    """Get metadata for shared media (only if enabled)"""
    shared_limiter.check(request)
    media = db.query(Media).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    if not media:
        raise HTTPException(status_code=404, detail="Shared media not found")
    
    if not media.share_ai_metadata:
        raise HTTPException(status_code=403, detail="AI metadata not shared")
    
    file_path = settings.BASE_DIR / media.path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    
    return extract_media_metadata(file_path)

@router.get("/{share_uuid}/status")
async def get_shared_status(
    share_uuid: str, 
    request: Request, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Get status of shared media file (processing/ready)"""
    shared_limiter.check(request)
    media = db.query(Media).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    if not media:
        raise HTTPException(status_code=404, detail="Shared media not found")
        
    # Serve original file immediately if AI metadata is shared
    if media.share_ai_metadata:
        return {"status": "not_stripped"}
        
    file_path = settings.BASE_DIR / media.path
    if not file_path.exists():
        return {"status": "error"}
        
    status = get_media_cache_status(file_path, media.mime_type)
    
    # If processing (not in cache), trigger generation
    if status == 'processing':
        background_tasks.add_task(create_stripped_media_cache, file_path, media.mime_type)
        
    return {"status": status}
