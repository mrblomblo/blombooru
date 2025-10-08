from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from ..database import get_db
from ..models import Media
from ..config import settings
from ..schemas import MediaResponse

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
    
    # Use the same metadata extraction logic from media.py
    file_path = settings.BASE_DIR / media.path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    
    metadata = {}
    
    try:
        from PIL import Image
        
        with Image.open(file_path) as img:
            if hasattr(img, 'info'):
                for key, value in img.info.items():
                    if key.lower() in ['parameters', 'prompt', 'comment', 'usercomment']:
                        try:
                            import json
                            metadata[key] = json.loads(value)
                        except:
                            metadata[key] = value
            
            if hasattr(img, 'getexif'):
                exif = img.getexif()
                if exif and 0x9286 in exif:
                    try:
                        import json
                        metadata['parameters'] = json.loads(exif[0x9286])
                    except:
                        metadata['parameters'] = exif[0x9286]
        
        return metadata
        
    except Exception as e:
        print(f"Error reading metadata: {e}")
        return {}
