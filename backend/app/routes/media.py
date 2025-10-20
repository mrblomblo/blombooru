from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, text, or_, and_
from typing import List, Optional
import uuid
import shutil
import hashlib
from pathlib import Path
from PIL import Image
import json
from ..database import get_db
from ..auth import require_admin_mode, get_current_user
from ..models import Media, Tag, User, blombooru_media_tags
from ..schemas import MediaResponse, MediaUpdate, MediaCreate, RatingEnum
from ..config import settings
from ..utils.media_processor import process_media_file, calculate_file_hash
from ..utils.thumbnail_generator import generate_thumbnail

router = APIRouter(prefix="/api/media", tags=["media"])

def update_tag_counts(db: Session, tag_ids: List[int]):
    """Update post counts for given tags"""
    for tag_id in tag_ids:
        count = db.query(blombooru_media_tags).filter(
            blombooru_media_tags.c.tag_id == tag_id
        ).count()
        
        db.query(Tag).filter(Tag.id == tag_id).update(
            {"post_count": count},
            synchronize_session=False
        )
        
def get_or_create_tags(db: Session, tag_names: List[str]) -> List[Tag]:
    """Get or create tags by name"""
    tags = []
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name, post_count=0)
            db.add(tag)
            db.flush()
        tags.append(tag)
    
    return tags

@router.get("/")
async def get_media_list(
    page: int = 1,
    limit: int = Query(None),
    rating: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get paginated media list"""
    if limit is None:
        limit = settings.get_items_per_page()
    
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
                        # Handle byte strings
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
                                user_comment = user_comment.decode('utf-8', errors='ignore')
                                # Remove any null bytes or special characters
                                user_comment = user_comment.replace('\x00', '').strip()
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
                    
                    # XPComment tag (0x9C9C) - Windows comment field
                    if 0x9C9C in exif:
                        xp_comment = exif[0x9C9C]
                        if isinstance(xp_comment, bytes):
                            try:
                                # XPComment is UTF-16LE encoded
                                decoded = xp_comment.decode('utf-16le', errors='ignore').replace('\x00', '').strip()
                                if decoded:
                                    try:
                                        metadata['parameters'] = json.loads(decoded)
                                    except (json.JSONDecodeError, ValueError):
                                        metadata['parameters'] = decoded
                            except:
                                pass
                    
                    # XPKeywords tag (0x9C9E)
                    if 0x9C9E in exif:
                        xp_keywords = exif[0x9C9E]
                        if isinstance(xp_keywords, bytes):
                            try:
                                decoded = xp_keywords.decode('utf-16le', errors='ignore').replace('\x00', '').strip()
                                if decoded:
                                    try:
                                        metadata['keywords'] = json.loads(decoded)
                                    except (json.JSONDecodeError, ValueError):
                                        metadata['keywords'] = decoded
                            except:
                                pass
            
            # For WebP specifically, try to get XMP data
            if img.format == 'WEBP' and hasattr(img, 'getxmp'):
                try:
                    xmp_data = img.getxmp()
                    if xmp_data:
                        metadata['xmp'] = xmp_data
                except:
                    pass
            
            # Legacy EXIF method (for older PIL versions)
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
        print(f"Error reading metadata for media {media_id}: {e}")
        import traceback
        traceback.print_exc()
        return {}

@router.post("/", response_model=MediaResponse)
async def upload_media(
    file: UploadFile = File(None),
    scanned_path: Optional[str] = Form(None),
    rating: RatingEnum = Form(RatingEnum.safe),
    tags: str = Form(""),
    source: Optional[str] = Form(None),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Upload new media"""
    try:
        # Check if this is a scanned file import or regular upload
        if scanned_path:
            # SCANNED FILE - use in place, don't copy
            file_path = Path(scanned_path)
            
            # Security check - ensure file is within ORIGINAL_DIR
            if not file_path.is_absolute():
                raise HTTPException(status_code=400, detail="Invalid file path")
            
            try:
                file_path = file_path.resolve()
                file_path.relative_to(settings.ORIGINAL_DIR.resolve())
            except (ValueError, FileNotFoundError):
                raise HTTPException(status_code=403, detail="Access denied")
            
            if not file_path.exists() or not file_path.is_file():
                raise HTTPException(status_code=404, detail="File not found")
            
            # Calculate hash from existing file
            file_hash = calculate_file_hash(file_path)
            unique_filename = file_path.name  # Keep original name
            
        else:
            # REGULAR UPLOAD - save with unique filename
            if not file:
                raise HTTPException(status_code=400, detail="Either file or scanned_path is required")
            
            # Read file contents to calculate hash first
            contents = await file.read()
            file_hash = hashlib.sha256(contents).hexdigest()
            
            # Generate UUID for the file
            media_uuid = str(uuid.uuid4())
            
            # Sanitize and get unique filename for the original file
            def sanitize_filename(filename: str) -> str:
                """Sanitize filename to be safe for filesystem and web"""
                path = Path(filename)
                stem = path.stem
                ext = path.suffix.lower()
                
                # Replace problematic characters with underscores
                # Keep alphanumeric, spaces, hyphens, underscores, and dots
                import re
                stem = re.sub(r'[^\w\s\-\.]', '_', stem)
                # Replace multiple spaces/underscores with single underscore
                stem = re.sub(r'[\s_]+', '_', stem)
                # Remove leading/trailing underscores
                stem = stem.strip('_')
                
                # If stem is empty after sanitization, use the UUID
                if not stem:
                    stem = media_uuid
                
                return f"{stem}{ext}"
            
            def get_unique_filename(directory: Path, filename: str) -> str:
                """Get a unique filename in the directory by appending a number if needed"""
                sanitized = sanitize_filename(filename)
                path = directory / sanitized
                
                if not path.exists():
                    return sanitized
                
                # File exists, add a number suffix
                stem = Path(sanitized).stem
                ext = Path(sanitized).suffix
                counter = 1
                
                while True:
                    new_filename = f"{stem}_{counter}{ext}"
                    new_path = directory / new_filename
                    if not new_path.exists():
                        return new_filename
                    counter += 1
            
            # Get unique filename preserving original name
            unique_filename = get_unique_filename(settings.ORIGINAL_DIR, file.filename)
            file_path = settings.ORIGINAL_DIR / unique_filename
            
            print(f"Uploading file: {file.filename} -> {unique_filename}")
            
            # Save the uploaded file
            with open(file_path, 'wb') as buffer:
                buffer.write(contents)
            
            print(f"File saved to: {file_path}")
        
        # Check for duplicates AFTER we have the hash
        existing = db.query(Media).filter(Media.hash == file_hash).first()
        if existing:
            print(f"Duplicate file detected: {file_hash}")
            # Only delete uploaded file if it was a new upload (not scanned)
            if not scanned_path and file_path.exists():
                file_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=409, 
                detail=f"Media already exists (duplicate of {existing.filename})"
            )
        
        # Process media
        metadata = process_media_file(file_path)
        print(f"Media processed: {metadata}")

        # Generate thumbnail with same name as media file (but .jpg extension)
        thumbnail_name = Path(unique_filename).stem
        thumbnail_filename = f"{thumbnail_name}.jpg"
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
        
        # Create media record with the filename (original for scanned, unique for uploaded)
        relative_path = file_path.relative_to(settings.BASE_DIR)
        relative_thumb = thumbnail_path.relative_to(settings.BASE_DIR) if thumbnail_generated else None
        
        media = Media(
            filename=unique_filename,
            path=str(relative_path),
            thumbnail_path=str(relative_thumb) if relative_thumb else None,
            hash=file_hash,
            file_type=metadata['file_type'],
            mime_type=metadata['mime_type'],
            file_size=metadata['file_size'],
            width=metadata['width'],
            height=metadata['height'],
            duration=metadata['duration'],
            rating=rating,
            source=source if source else None
        )
        
        # Add tags
        tag_ids = []
        if tags:
            tag_list = [t.strip() for t in tags.split() if t.strip()]
            media.tags = get_or_create_tags(db, tag_list)
            tag_ids = [tag.id for tag in media.tags]
            print(f"Tags added: {tag_list}")
        
        db.add(media)
        db.commit()
        db.refresh(media)
        
        if tag_ids:
            update_tag_counts(db, tag_ids)
            db.commit()
            db.refresh(media)
        
        print(f"Media uploaded successfully: ID={media.id}, Filename={unique_filename}")
        
        return MediaResponse.model_validate(media)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading media: {e}")
        import traceback
        traceback.print_exc()
        
        # Clean up files on error (but only if it was a new upload, not scanned)
        if not scanned_path:
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
    
    if 'source' in updates.model_fields_set:
        media.source = updates.source if updates.source else None
    
    affected_tag_ids = []
    if updates.tags is not None:
        # Get old tag IDs
        old_tag_ids = [tag.id for tag in media.tags]
        
        # Update tags
        media.tags = get_or_create_tags(db, updates.tags)
        
        # Get new tag IDs
        new_tag_ids = [tag.id for tag in media.tags]
        
        # All tags that need count updates
        affected_tag_ids = list(set(old_tag_ids + new_tag_ids))
    
    db.commit()
    
    # Update tag counts AFTER commit
    if affected_tag_ids:
        update_tag_counts(db, affected_tag_ids)
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
    
    # Get tag IDs before deletion
    tag_ids = [tag.id for tag in media.tags]
    
    # Delete files
    file_path = settings.BASE_DIR / media.path
    file_path.unlink(missing_ok=True)
    
    if media.thumbnail_path:
        thumb_path = settings.BASE_DIR / media.thumbnail_path
        thumb_path.unlink(missing_ok=True)
    
    db.delete(media)
    db.commit()
    
    # Update tag counts after deletion
    if tag_ids:
        update_tag_counts(db, tag_ids)
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
