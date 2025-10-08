from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, text, or_, and_
from typing import List, Optional
import uuid
import shutil
import hashlib
from pathlib import Path
from PIL import Image
from ..database import get_db
from ..auth import require_admin_mode, get_current_user
from ..models import Media, Tag, User, blombooru_media_tags
from ..schemas import MediaResponse, MediaUpdate, MediaCreate, RatingEnum
from ..config import settings
from ..utils.media_processor import process_media_file
from ..utils.thumbnail_generator import generate_thumbnail

router = APIRouter(prefix="/api/media", tags=["media"])

def get_or_create_tags(db: Session, tag_names: List[str]) -> List[Tag]:
    """Get or create tags by name"""
    tags = []
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        tags.append(tag)
    
    return tags

@router.get("/")
async def get_media_list(
    page: int = 1,
    limit: int = 30,
    rating: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get paginated media list"""
    try:
        # Don't filter by is_shared - show all media in your private gallery
        query = db.query(Media)
        
        # Filter by rating
        if rating and rating != "explicit":
            allowed_ratings = {
                "safe": [RatingEnum.safe],
                "questionable": [RatingEnum.safe, RatingEnum.questionable]
            }
            query = query.filter(Media.rating.in_(allowed_ratings.get(rating, [])))
        
        # Order by upload date
        query = query.order_by(desc(Media.uploaded_at))
        
        # Pagination
        offset = (page - 1) * limit
        total = query.count()
        media_list = query.offset(offset).limit(limit).all()
        
        # Convert to response models
        items = [MediaResponse.model_validate(m) for m in media_list]
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "pages": max(1, (total + limit - 1) // limit)
        }
    except Exception as e:
        print(f"Error in get_media_list: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{media_id}")
async def get_media(media_id: int, db: Session = Depends(get_db)):
    """Get media by ID"""
    media = db.query(Media).options(joinedload(Media.tags)).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    result = MediaResponse.model_validate(media).model_dump()
    result['share_ai_metadata'] = media.share_ai_metadata if hasattr(media, 'share_ai_metadata') else False
    return result

@router.get("/{media_id}/file")
async def get_media_file(media_id: int, db: Session = Depends(get_db)):
    """Serve media file"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    file_path = settings.BASE_DIR / media.path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path, media_type=media.mime_type)

@router.get("/{media_id}/thumbnail")
async def get_media_thumbnail(media_id: int, db: Session = Depends(get_db)):
    """Serve thumbnail"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media or not media.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    
    thumb_path = settings.BASE_DIR / media.thumbnail_path
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file not found")
    
    return FileResponse(thumb_path, media_type="image/jpeg")

@router.get("/{media_id}/metadata")
async def get_media_metadata(
    media_id: int,
    db: Session = Depends(get_db)
):
    """Get media file metadata (EXIF, parameters, etc.)"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    file_path = settings.BASE_DIR / media.path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    
    metadata = {}
    
    try:
        from PIL import Image
        
        with Image.open(file_path) as img:
            # Get EXIF data if available
            if hasattr(img, '_getexif') and img._getexif():
                metadata['exif'] = img._getexif()
            
            # Get PNG text chunks (where AI params are often stored)
            if hasattr(img, 'info'):
                for key, value in img.info.items():
                    # Common keys: parameters, Parameters, prompt, etc.
                    if key.lower() in ['parameters', 'prompt', 'comment', 'usercomment']:
                        try:
                            # Try to parse as JSON
                            import json
                            metadata[key] = json.loads(value)
                        except:
                            # If not JSON, store as string
                            metadata[key] = value
            
            # For WebP and other formats, check for XMP/EXIF
            if hasattr(img, 'getexif'):
                exif = img.getexif()
                if exif:
                    # Check for UserComment (often contains AI params)
                    if 0x9286 in exif:  # UserComment tag
                        try:
                            import json
                            metadata['parameters'] = json.loads(exif[0x9286])
                        except:
                            metadata['parameters'] = exif[0x9286]
        
        return metadata
        
    except Exception as e:
        print(f"Error reading metadata: {e}")
        return {}

@router.post("/", response_model=MediaResponse)
async def upload_media(
    file: UploadFile = File(...),
    rating: RatingEnum = Form(RatingEnum.safe),
    tags: str = Form(""),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Upload new media"""
    try:
        # Read file contents to calculate hash first
        contents = await file.read()
        file_hash = hashlib.sha256(contents).hexdigest()
        
        # Check for duplicates BEFORE saving file
        existing = db.query(Media).filter(Media.hash == file_hash).first()
        if existing:
            print(f"Duplicate file detected: {file_hash}")
            raise HTTPException(
                status_code=409, 
                detail=f"Media already exists (duplicate of {existing.filename})"
            )
        
        # Generate a single UUID for this upload
        media_uuid = str(uuid.uuid4())
        
        # Save original file with UUID + original extension
        file_ext = Path(file.filename).suffix.lower()
        unique_filename = f"{media_uuid}{file_ext}"
        file_path = settings.ORIGINAL_DIR / unique_filename
        
        print(f"Uploading file: {file.filename} -> {unique_filename}")
        
        with open(file_path, 'wb') as buffer:
            buffer.write(contents)
        
        print(f"File saved to: {file_path}")
        
        # Process media
        metadata = process_media_file(file_path)
        print(f"Media processed: {metadata}")
        
        # Generate thumbnail with same UUID
        thumbnail_filename = f"{media_uuid}.jpg"
        thumbnail_path = settings.THUMBNAIL_DIR / thumbnail_filename
        
        print(f"Generating thumbnail: {thumbnail_filename}")
        
        thumbnail_generated = generate_thumbnail(
            file_path,
            thumbnail_path,
            metadata['file_type']
        )
        
        if thumbnail_generated:
            print(f"Thumbnail generated: {thumbnail_path}")
        else:
            print(f"Warning: Thumbnail generation failed")
        
        # Create media record
        relative_path = file_path.relative_to(settings.BASE_DIR)
        relative_thumb = thumbnail_path.relative_to(settings.BASE_DIR) if thumbnail_generated else None
        
        media = Media(
            filename=file.filename,
            path=str(relative_path),
            thumbnail_path=str(relative_thumb) if relative_thumb else None,
            hash=file_hash,
            file_type=metadata['file_type'],
            mime_type=metadata['mime_type'],
            file_size=metadata['file_size'],
            width=metadata['width'],
            height=metadata['height'],
            duration=metadata['duration'],
            rating=rating
        )
        
        # Add tags
        if tags:
            tag_list = [t.strip() for t in tags.split() if t.strip()]
            media.tags = get_or_create_tags(db, tag_list)
            print(f"Tags added: {tag_list}")
        
        db.add(media)
        db.commit()
        db.refresh(media)
        
        # Update tag counts
        for tag in media.tags:
            tag.post_count = db.query(Media).join(blombooru_media_tags).filter(
                blombooru_media_tags.c.tag_id == tag.id
            ).count()
        db.commit()
        
        print(f"Media uploaded successfully: ID={media.id}")
        
        return MediaResponse.model_validate(media)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading media: {e}")
        import traceback
        traceback.print_exc()
        
        # Clean up files on error
        if 'file_path' in locals() and file_path.exists():
            file_path.unlink(missing_ok=True)
        if 'thumbnail_path' in locals() and thumbnail_path.exists():
            thumbnail_path.unlink(missing_ok=True)
            
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.patch("/{media_id}", response_model=MediaResponse)
async def update_media(
    media_id: int,
    updates: MediaUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Update media metadata"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Update fields
    if updates.rating:
        media.rating = updates.rating
    
    if updates.tags is not None:
        # Remove old tag associations
        old_tags = media.tags.copy()
        media.tags = get_or_create_tags(db, updates.tags)
        
        # Update tag counts
        all_affected_tags = set(old_tags + media.tags)
        for tag in all_affected_tags:
            tag.post_count = db.query(Media).join(blombooru_media_tags).filter(
                blombooru_media_tags.c.tag_id == tag.id
            ).count()
    
    db.commit()
    db.refresh(media)
    return MediaResponse.model_validate(media)

@router.delete("/{media_id}")
async def delete_media(
    media_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Delete media"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Delete files
    file_path = settings.BASE_DIR / media.path
    file_path.unlink(missing_ok=True)
    
    if media.thumbnail_path:
        thumb_path = settings.BASE_DIR / media.thumbnail_path
        thumb_path.unlink(missing_ok=True)
    
    # Update tag counts before deletion
    for tag in media.tags:
        tag.post_count = max(0, tag.post_count - 1)
    
    db.delete(media)
    db.commit()
    
    return {"message": "Media deleted successfully"}

@router.post("/{media_id}/share")
async def share_media(
    media_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Create or update share link for media"""
    from fastapi import Query
    from ..database import get_db
    
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    if not media.is_shared:
        import uuid
        media.share_uuid = str(uuid.uuid4())
        media.is_shared = True
    
    db.commit()
    
    return {
        "share_url": f"/shared/{media.share_uuid}",
        "share_ai_metadata": media.share_ai_metadata if hasattr(media, 'share_ai_metadata') else False
    }

@router.delete("/{media_id}/share")
async def unshare_media(
    media_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Remove share link for media"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    media.is_shared = False
    media.share_uuid = None
    db.commit()
    
    return {"message": "Share removed"}

@router.patch("/{media_id}/share-settings")
async def update_share_settings(
    media_id: int,
    share_ai_metadata: bool,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Update share settings for media"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    if not media.is_shared:
        raise HTTPException(status_code=400, detail="Media is not shared")
    
    media.share_ai_metadata = share_ai_metadata
    db.commit()
    
    return {
        "share_ai_metadata": media.share_ai_metadata
    }

@router.post("/extract-archive")
async def extract_archive(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_mode)
):
    """Extract files from zip or tar.gz archive"""
    import zipfile
    import tarfile
    import tempfile
    import base64
    from pathlib import Path
    
    # Security: limit file size (100MB max for archives)
    MAX_ARCHIVE_SIZE = 100 * 1024 * 1024
    MAX_EXTRACTED_SIZE = 500 * 1024 * 1024
    
    contents = await file.read()
    if len(contents) > MAX_ARCHIVE_SIZE:
        raise HTTPException(status_code=400, detail="Archive too large (max 100MB)")
    
    extracted_files = []
    total_size = 0
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            archive_path = temp_path / file.filename
            
            # Write archive to temp file
            with open(archive_path, 'wb') as f:
                f.write(contents)
            
            # Extract based on file type
            if file.filename.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    # Security: check for path traversal
                    for member in zip_ref.namelist():
                        if member.startswith('/') or '..' in member:
                            raise HTTPException(status_code=400, detail="Invalid file path in archive")
                    
                    zip_ref.extractall(temp_path)
                    
            elif file.filename.endswith(('.tar.gz', '.tgz')):
                with tarfile.open(archive_path, 'r:gz') as tar_ref:
                    # Security: check for path traversal
                    for member in tar_ref.getmembers():
                        if member.name.startswith('/') or '..' in member.name:
                            raise HTTPException(status_code=400, detail="Invalid file path in archive")
                    
                    tar_ref.extractall(temp_path)
            else:
                raise HTTPException(status_code=400, detail="Unsupported archive format")
            
            # Process extracted files
            for extracted_file in temp_path.rglob('*'):
                if extracted_file.is_file() and extracted_file != archive_path:
                    # Security: check total extracted size
                    file_size = extracted_file.stat().st_size
                    total_size += file_size
                    
                    if total_size > MAX_EXTRACTED_SIZE:
                        raise HTTPException(status_code=400, detail="Extracted files too large (max 500MB)")
                    
                    # Read file content
                    with open(extracted_file, 'rb') as f:
                        file_content = f.read()
                    
                    # Determine MIME type
                    import mimetypes
                    mime_type, _ = mimetypes.guess_type(extracted_file.name)
                    
                    # Only include valid media files
                    valid_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'video/mp4', 'video/webm']
                    if mime_type in valid_types:
                        extracted_files.append({
                            'filename': extracted_file.name,
                            'mime_type': mime_type,
                            'content': base64.b64encode(file_content).decode('utf-8')
                        })
            
            return {
                'files': extracted_files,
                'count': len(extracted_files)
            }
            
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid or corrupted zip file")
    except tarfile.TarError:
        raise HTTPException(status_code=400, detail="Invalid or corrupted tar.gz file")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error extracting archive: {str(e)}")
