from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import desc, text, or_, and_, func
from typing import List, Optional
import uuid
import shutil
import hashlib
from pathlib import Path
from PIL import Image
import json
from ..database import get_db
from ..auth import require_admin_mode, get_current_user
from ..models import Media, Tag, User, blombooru_media_tags, Album, blombooru_album_media
from ..schemas import MediaResponse, MediaUpdate, MediaCreate, RatingEnum, AlbumListResponse, ShareSettingsUpdate
from ..config import settings
from ..utils.media_processor import process_media_file, calculate_file_hash
from ..utils.thumbnail_generator import generate_thumbnail
from ..utils.media_helpers import extract_image_metadata, serve_media_file, sanitize_filename, get_unique_filename, delete_media_cache, create_stripped_media_cache
from ..utils.album_utils import get_random_thumbnails, get_album_rating, get_media_count, update_album_last_modified
from ..utils.cache import cache_response, invalidate_media_cache, invalidate_tag_cache, invalidate_album_cache, invalidate_media_item_cache

router = APIRouter(prefix="/api/media", tags=["media"])

def update_tag_counts(db: Session, tag_ids: List[int]):
    """Update post counts for given tags"""
    if not tag_ids:
        return
    counts = db.query(
        blombooru_media_tags.c.tag_id,
        func.count(blombooru_media_tags.c.media_id)
    ).filter(
        blombooru_media_tags.c.tag_id.in_(tag_ids)
    ).group_by(blombooru_media_tags.c.tag_id).all()
    count_map = dict(counts)
    for tag_id in tag_ids:
        db.query(Tag).filter(Tag.id == tag_id).update(
            {"post_count": count_map.get(tag_id, 0)},
            synchronize_session=False
        )
        
def get_or_create_tags(db: Session, tag_names: List[str], category_hints: Optional[dict] = None) -> List[Tag]:
    """Get or create tags by name.
    
    Args:
        db: Database session
        tag_names: List of tag name strings
        category_hints: Optional dict mapping tag names to category strings
                       (e.g. {"artist_name": "artist", "char_name": "character"}).
                       When a tag doesn't exist and a hint is provided, the tag
                       is created with that category instead of the default "general".
    """
    tags = []
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            category = "general"
            if category_hints and name in category_hints:
                category = category_hints[name]
            tag = Tag(name=name, post_count=0, category=category)
            db.add(tag)
            db.flush()
        tags.append(tag)
    
    return tags

@router.get("/")
@router.get("")
@cache_response(expire=300, key_prefix="media_list")
async def get_media_list(
    request: Request,
    page: int = 1,
    limit: int = Query(None),
    rating: Optional[str] = None,
    sort: Optional[str] = None,
    order: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get paginated media list"""
    if limit is None:
        limit = settings.get_items_per_page()
    
    try:
        query = db.query(Media).options(selectinload(Media.tags))
        
        if rating and rating != "explicit":
            allowed_ratings = {
                "safe": [RatingEnum.safe],
                "questionable": [RatingEnum.safe, RatingEnum.questionable]
            }
            query = query.filter(Media.rating.in_(allowed_ratings.get(rating, [])))
        
        # Sorting
        sort_by = sort if sort else settings.get_default_sort()
        sort_order = order if order else settings.get_default_order()
        
        sort_column = Media.uploaded_at
        if sort_by == 'filename':
            sort_column = Media.filename
        elif sort_by == 'file_size':
            sort_column = Media.file_size
        elif sort_by == 'file_type':
            sort_column = Media.file_type
            
        if sort_order == 'asc':
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())
        
        # Pagination
        offset = (page - 1) * limit
        total = query.count()
        media_list = query.offset(offset).limit(limit).all()
        
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

@router.get("/batch")
async def get_media_batch(
    ids: str = Query(..., description="Comma-separated list of media IDs"),
    db: Session = Depends(get_db)
):
    """Get multiple media items by their IDs in a single request"""
    try:
        media_ids = [int(id_str.strip()) for id_str in ids.split(",") if id_str.strip().isdigit()]
        if not media_ids:
            return {"items": []}
            
        media_list = db.query(Media).options(selectinload(Media.tags)).filter(Media.id.in_(media_ids)).all()
        items = [MediaResponse.model_validate(m) for m in media_list]
        
        return {"items": items}
    except Exception as e:
        print(f"Error in get_media_batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{media_id}")
async def get_media(media_id: int, db: Session = Depends(get_db)):
    """Get media by ID"""
    media = db.query(Media).options(joinedload(Media.tags)).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    result = MediaResponse.model_validate(media).model_dump()
    result['share_ai_metadata'] = media.share_ai_metadata if hasattr(media, 'share_ai_metadata') else False
    
    # Add parent and siblings info
    hierarchy = []
    if media.parent_id:
        # I am a child
        related = db.query(Media).filter(
            or_(
                Media.id == media.parent_id,
                and_(Media.parent_id == media.parent_id, Media.id != media.id)
            )
        ).all()
        hierarchy = [MediaResponse.model_validate(r).model_dump() for r in related]
    else:
        # I might be a parent
        children = db.query(Media).filter(Media.parent_id == media.id).all()
        hierarchy = [MediaResponse.model_validate(c).model_dump() for c in children]
    
    result['hierarchy'] = hierarchy
    return result

@router.get("/{media_id}/file")
async def get_media_file(media_id: int, db: Session = Depends(get_db)):
    """Serve media file"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    file_path = settings.BASE_DIR / media.path
    return await serve_media_file(file_path, media.mime_type)

@router.get("/{media_id}/thumbnail")
async def get_media_thumbnail(media_id: int, db: Session = Depends(get_db)):
    """Serve thumbnail"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media or not media.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    
    thumb_path = settings.BASE_DIR / media.thumbnail_path
    return await serve_media_file(thumb_path, "image/jpeg", "Thumbnail file not found")

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
    
    return extract_image_metadata(file_path)

@router.post("/", response_model=MediaResponse)
async def upload_media(
    file: UploadFile = File(None),
    scanned_path: Optional[str] = Form(None),
    rating: RatingEnum = Form(RatingEnum.safe),
    tags: str = Form(""),
    album_ids: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    category_hints: Optional[str] = Form(None),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Upload new media"""
    try:
        if scanned_path:
            # SCANNED FILE 
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
            # REGULAR UPLOAD
            if not file:
                raise HTTPException(status_code=400, detail="Either file or scanned_path is required")
            
            contents = await file.read()
            file_hash = hashlib.sha256(contents).hexdigest()
            media_uuid = str(uuid.uuid4())
            
            unique_filename = get_unique_filename(settings.ORIGINAL_DIR, file.filename)
            file_path = settings.ORIGINAL_DIR / unique_filename
            
            print(f"Uploading file: {file.filename} -> {unique_filename}")
            
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
        
        metadata = process_media_file(file_path)
        print(f"Media processed: {metadata}")

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
            source=source if source else None,
        )
        
        tag_ids_to_update = []
        if tags:
            tag_list = [t.strip() for t in tags.split() if t.strip()]
            parsed_hints = None
            if category_hints:
                try:
                    import json
                    parsed_hints = json.loads(category_hints)
                except (json.JSONDecodeError, TypeError):
                    pass
            media.tags = get_or_create_tags(db, tag_list, category_hints=parsed_hints)
            tag_ids_to_update = [tag.id for tag in media.tags]
            print(f"Tags added: {tag_list}")
            
        # Handle Album IDs
        affected_album_ids = []
        if album_ids:
            try:
                a_ids = [int(id_str.strip()) for id_str in album_ids.split(",") if id_str.strip().isdigit()]
                if a_ids:
                    albums = db.query(Album).filter(Album.id.in_(a_ids)).all()
                    media.albums = albums
                    affected_album_ids = [album.id for album in albums]
                    print(f"Added to albums: {affected_album_ids}")
            except Exception as e:
                print(f"Error parsing album_ids: {e}")
        
        db.add(media)
        db.commit()
        db.refresh(media)
        
        if tag_ids_to_update:
            update_tag_counts(db, tag_ids_to_update)
            db.commit()
            
        if affected_album_ids:
            for a_id in affected_album_ids:
                update_album_last_modified(a_id, db)
            db.commit()
            invalidate_album_cache()
            
        db.refresh(media)
        
        print(f"Media uploaded successfully: ID={media.id}, Filename={unique_filename}")
        
        invalidate_media_cache()
        invalidate_tag_cache()
        
        return MediaResponse.model_validate(media)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading media: {e}")
        import traceback
        traceback.print_exc()
        
        # Clean up files on error (only if it was a new upload, not scanned)
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
    
    if updates.rating:
        media.rating = updates.rating
    
    if 'source' in updates.model_fields_set:
        media.source = updates.source if updates.source else None
    
    affected_tag_ids = []
    if updates.tags is not None:
        old_tag_ids = [tag.id for tag in media.tags]
        media.tags = get_or_create_tags(db, updates.tags)
        new_tag_ids = [tag.id for tag in media.tags]
        affected_tag_ids = list(set(old_tag_ids + new_tag_ids))

    parent_id_changed = False
    old_parent_id = media.parent_id
    
    if 'parent_id' in updates.model_fields_set:
        if updates.parent_id:
            parent = db.query(Media).filter(Media.id == updates.parent_id).first()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent media not found")
            
            if db.query(Media).filter(Media.parent_id == media.id).first():
                raise HTTPException(status_code=400, detail="This item already has children and cannot be a child itself")
            
            if parent.parent_id:
                raise HTTPException(status_code=400, detail="The selected parent is already a child of another item")
            
            if updates.parent_id == media.id:
                raise HTTPException(status_code=400, detail="An item cannot be its own parent")
            
            if media.parent_id != updates.parent_id:
                parent_id_changed = True
            media.parent_id = updates.parent_id
        else:
            if media.parent_id is not None:
                parent_id_changed = True
            media.parent_id = None
    
    db.commit()
    
    if affected_tag_ids:
        update_tag_counts(db, affected_tag_ids)
        db.commit()
    
    db.refresh(media)
    
    if parent_id_changed:
        invalidate_media_item_cache(media_id)

        if old_parent_id:
            invalidate_media_item_cache(old_parent_id)

        if media.parent_id:
            invalidate_media_item_cache(media.parent_id)
    else:
        invalidate_media_cache()
        invalidate_tag_cache()
    
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
    
    tag_ids = [tag.id for tag in media.tags]
    
    file_path = settings.BASE_DIR / media.path
    file_path.unlink(missing_ok=True)
    
    if media.thumbnail_path:
        thumb_path = settings.BASE_DIR / media.thumbnail_path
        thumb_path.unlink(missing_ok=True)
    
    db.delete(media)
    db.commit()
    
    if tag_ids:
        update_tag_counts(db, tag_ids)
        db.commit()

    invalidate_media_cache()
    invalidate_tag_cache()
    
    return {"message": "Media deleted successfully"}

@router.post("/{media_id}/share")
async def share_media(
    media_id: int,
    background_tasks: BackgroundTasks,
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
        
        # Trigger background stripping
        if media.mime_type and media.mime_type.startswith('image/'):
            file_path = settings.BASE_DIR / media.path
            background_tasks.add_task(create_stripped_media_cache, file_path, media.mime_type)
    
    db.commit()
    invalidate_media_item_cache(media_id)
    
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
    invalidate_media_item_cache(media_id)
    
    # Cleanup cache
    try:
        file_path = settings.BASE_DIR / media.path
        delete_media_cache(file_path)
    except Exception as e:
        print(f"Failed to cleanup cache for unshared media: {e}")
    
    return {"message": "Share removed"}

@router.patch("/{media_id}/share-settings")
async def update_share_settings(
    media_id: int,
    updates: ShareSettingsUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Update share settings for media"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    if not media.is_shared:
        raise HTTPException(status_code=400, detail="Media is not shared")
    
    if updates.share_ai_metadata is not None:
        media.share_ai_metadata = updates.share_ai_metadata
        
    if updates.share_language is not None:
        if updates.share_language == "default" or updates.share_language == "":
            media.share_language = None
        else:
            media.share_language = updates.share_language
            
    db.commit()
    invalidate_media_item_cache(media_id)
    
    return {
        "share_ai_metadata": media.share_ai_metadata,
        "share_language": media.share_language
    }

@router.get("/{media_id}/albums")
async def get_media_albums(
    media_id: int,
    db: Session = Depends(get_db)
):
    """Get all albums containing a specific media item"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    albums = db.query(Album).join(
        blombooru_album_media,
        Album.id == blombooru_album_media.c.album_id
    ).filter(
        blombooru_album_media.c.media_id == media_id
    ).all()
    
    result = []
    for album in albums:
        thumbnails = get_random_thumbnails(album.id, db, count=4)
        album_rating = get_album_rating(album.id, db)
        media_count = get_media_count(album.id, db)
        
        result.append(AlbumListResponse(
            id=album.id,
            name=album.name,
            last_modified=album.last_modified,
            thumbnail_paths=thumbnails,
            rating=album_rating,
            media_count=media_count
        ))
    
    return {"albums": result}

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
                if extracted_file.is_symlink():
                    continue
                    
                if extracted_file.is_file() and extracted_file != archive_path:
                    # Security: check total extracted size
                    file_size = extracted_file.stat().st_size
                    total_size += file_size
                    
                    if total_size > MAX_EXTRACTED_SIZE:
                        raise HTTPException(status_code=400, detail="Extracted files too large (max 500MB)")
                    
                    with open(extracted_file, 'rb') as f:
                        file_content = f.read()
                    
                    import mimetypes
                    mime_type, _ = mimetypes.guess_type(extracted_file.name)
                    
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
