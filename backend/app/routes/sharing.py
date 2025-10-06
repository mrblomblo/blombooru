from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Media
from ..config import settings

router = APIRouter(prefix="/api/shared", tags=["sharing"])

@router.get("/{share_uuid}")
async def get_shared_content(share_uuid: str, db: Session = Depends(get_db)):
    """Get shared media"""
    # Check if it's a media share
    media = db.query(Media).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    if media:
        return {
            "type": "media",
            "data": media
        }

    raise HTTPException(status_code=404, detail="Shared content not found")

@router.get("/{share_uuid}/file")
async def get_shared_file(share_uuid: str, db: Session = Depends(get_db)):
    """Serve shared media file (metadata stripped handled by frontend)"""
    media = db.query(Media).filter(
        Media.share_uuid == share_uuid,
        Media.is_shared == True
    ).first()
    
    if not media:
        raise HTTPException(status_code=404, detail="Shared media not found")
    
    file_path = settings.BASE_DIR / media.path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Note: For true metadata stripping, you'd want to process the image
    # and strip EXIF data before serving. For now, serving as-is.
    return FileResponse(file_path, media_type=media.mime_type)

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
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file not found")
    
    return FileResponse(thumb_path, media_type="image/jpeg")
