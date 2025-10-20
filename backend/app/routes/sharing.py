from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from PIL import Image
import json
from ..database import get_db
from ..models import Media
from ..config import settings
from ..schemas import MediaResponse
from ..utils.media_helpers import extract_media_metadata, serve_media_file

router = APIRouter(prefix="/api/shared", tags=["sharing"])

@router.get("/{share_uuid}")
async def get_shared_content(share_uuid: str, db: Session = Depends(get_db)):
    """Get shared media"""
    # Check if it's a media share
    media = db.query(Media).options(joinedload(Media.tags)).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    if media:
        media_dict = MediaResponse.model_validate(media).model_dump()
        media_dict['share_ai_metadata'] = media.share_ai_metadata
        
        return {
            "type": "media",
            "data": media_dict
        }

    raise HTTPException(status_code=404, detail="Shared content not found")

@router.get("/{share_uuid}/file")
async def get_shared_file(share_uuid: str, db: Session = Depends(get_db)):
    """Serve shared media file with metadata stripped if AI metadata not shared"""
    media = db.query(Media).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    if not media:
        raise HTTPException(status_code=404, detail="Shared media not found")
    
    file_path = settings.BASE_DIR / media.path
    # Strip metadata when AI metadata sharing is disabled
    strip_metadata = not media.share_ai_metadata
    
    return serve_media_file(file_path, media.mime_type, strip_metadata=strip_metadata)

@router.get("/{share_uuid}/thumbnail")
async def get_shared_thumbnail(share_uuid: str, db: Session = Depends(get_db)):
    """Serve shared media thumbnail"""
    media = db.query(Media).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    if not media or not media.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    
    thumb_path = settings.BASE_DIR / media.thumbnail_path
    return serve_media_file(thumb_path, "image/jpeg", "Thumbnail file not found")

@router.get("/{share_uuid}/metadata")
async def get_shared_metadata(share_uuid: str, db: Session = Depends(get_db)):
    """Get metadata for shared media (only if enabled)"""
    media = db.query(Media).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    if not media:
        raise HTTPException(status_code=404, detail="Shared media not found")
    
    # Check if AI metadata sharing is enabled
    if not media.share_ai_metadata:
        raise HTTPException(status_code=403, detail="AI metadata not shared")
    
    file_path = settings.BASE_DIR / media.path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    
    return extract_media_metadata(file_path)
