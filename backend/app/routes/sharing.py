from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from PIL import Image
import json
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
    
    file_path = settings.BASE_DIR / media.path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    
    metadata = {}
    
    try:
        with Image.open(file_path) as img:
            # Get PNG text chunks (ComfyUI, A1111, SwarmUI often use these)
            if hasattr(img, 'info') and img.info:
                for key, value in img.info.items():
                    # Store all text chunks
                    if isinstance(value, str):
                        # Try to parse as JSON first
                        try:
                            metadata[key] = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            # Store as string if not valid JSON
                            metadata[key] = value
                    elif isinstance(value, bytes):
                        try:
                            decoded = value.decode('utf-8', errors='ignore')
                            try:
                                metadata[key] = json.loads(decoded)
                            except (json.JSONDecodeError, ValueError):
                                metadata[key] = decoded
                        except:
                            pass
                    else:
                        metadata[key] = value
            
            # Get EXIF data (for JPEG, WebP, etc.)
            if hasattr(img, 'getexif'):
                exif = img.getexif()
                if exif:
                    # UserComment tag (0x9286) - often contains AI parameters
                    if 0x9286 in exif:
                        user_comment = exif[0x9286]
                        # Handle bytes
                        if isinstance(user_comment, bytes):
                            try:
                                user_comment = user_comment.decode('utf-8', errors='ignore').replace('\x00', '').strip()
                            except:
                                pass
                        
                        # Try to parse as JSON
                        if isinstance(user_comment, str) and user_comment:
                            try:
                                metadata['parameters'] = json.loads(user_comment)
                            except (json.JSONDecodeError, ValueError):
                                metadata['parameters'] = user_comment
                    
                    # ImageDescription tag (0x010E) - sometimes used for metadata
                    if 0x010E in exif:
                        description = exif[0x010E]
                        if isinstance(description, bytes):
                            try:
                                description = description.decode('utf-8', errors='ignore').replace('\x00', '').strip()
                            except:
                                pass
                        
                        if isinstance(description, str) and description:
                            try:
                                parsed = json.loads(description)
                                # Merge with metadata
                                if isinstance(parsed, dict):
                                    metadata.update(parsed)
                                else:
                                    metadata['description'] = parsed
                            except (json.JSONDecodeError, ValueError):
                                metadata['description'] = description
                    
                    # XPComment tag
                    if 0x9C9C in exif:
                        xp_comment = exif[0x9C9C]
                        if isinstance(xp_comment, bytes):
                            try:
                                decoded = xp_comment.decode('utf-16le', errors='ignore').replace('\x00', '').strip()
                                if decoded:
                                    try:
                                        metadata['parameters'] = json.loads(decoded)
                                    except (json.JSONDecodeError, ValueError):
                                        metadata['parameters'] = decoded
                            except:
                                pass
            
            # WebP XMP data
            if img.format == 'WEBP' and hasattr(img, 'getxmp'):
                try:
                    xmp_data = img.getxmp()
                    if xmp_data:
                        metadata['xmp'] = xmp_data
                except:
                    pass
            
            # Legacy EXIF
            if hasattr(img, '_getexif') and callable(img._getexif):
                try:
                    legacy_exif = img._getexif()
                    if legacy_exif and 0x9286 in legacy_exif:
                        user_comment = legacy_exif[0x9286]
                        if isinstance(user_comment, bytes):
                            user_comment = user_comment.decode('utf-8', errors='ignore').replace('\x00', '').strip()
                        if isinstance(user_comment, str) and user_comment and 'parameters' not in metadata:
                            try:
                                metadata['parameters'] = json.loads(user_comment)
                            except (json.JSONDecodeError, ValueError):
                                metadata['parameters'] = user_comment
                except:
                    pass
        
        return metadata
        
    except Exception as e:
        print(f"Error reading shared metadata for {share_uuid}: {e}")
        import traceback
        traceback.print_exc()
        return {}
