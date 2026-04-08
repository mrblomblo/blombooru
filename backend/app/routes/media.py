import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                     HTTPException, Query, Request, UploadFile)
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy import and_, desc, func, or_, text
from sqlalchemy.orm import Session, joinedload, selectinload

from ..auth import get_current_user, require_admin_mode
from ..config import settings
from ..utils.request_helpers import safe_error_detail
from ..database import get_db
from ..models import (Album, Media, Tag, User, blombooru_album_media,
                      blombooru_media_tags)
from ..schemas import (AlbumListResponse, MediaCreate, MediaResponse,
                       MediaUpdate, RatingEnum, ShareSettingsUpdate)
from ..utils.album_utils import (get_album_rating, get_media_count,
                                 get_random_thumbnails,
                                 update_album_last_modified)
from ..utils.cache import (cache_response, invalidate_album_cache,
                           invalidate_media_cache, invalidate_media_item_cache,
                           invalidate_tag_cache)
from ..utils.logger import logger
from ..utils.media_helpers import (create_stripped_media_cache,
                                   delete_media_cache, extract_image_metadata,
                                   get_unique_filename, sanitize_filename,
                                   serve_media_file)
from ..utils.media_processor import calculate_file_hash, process_media_file
from ..utils.thumbnail_generator import generate_thumbnail

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
    seen = set()
    unique_names = []
    for name in tag_names:
        name = name.strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        unique_names.append(name)

    tags = []
    for name in unique_names:
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

def process_and_save_media(
    db: Session,
    file_path: Path,
    unique_filename: str,
    rating,
    tags: str,
    album_ids: Optional[str],
    source: Optional[str],
    category_hints: Optional[str],
) -> "MediaResponse":
    """Hash-check, thumbnail generation, DB insert, tag/album linking, and cache
    invalidation for a media file that is already on disk at *file_path*.

    Raises HTTPException 409 on duplicate hash.  Does NOT delete file_path on
    error. Callers are responsible for cleanup of files they created.
    """
    file_hash = calculate_file_hash(file_path)

    existing = db.query(Media).filter(Media.hash == file_hash).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Media already exists (duplicate of {existing.filename})",
        )

    metadata = process_media_file(file_path)
    logger.debug(f"Media processed: {metadata}")

    thumbnail_filename = Path(unique_filename).stem + ".jpg"
    thumbnail_path = settings.THUMBNAIL_DIR / thumbnail_filename

    logger.debug(f"Generating thumbnail: {thumbnail_filename}")
    thumbnail_generated = generate_thumbnail(file_path, thumbnail_path, metadata["file_type"])

    if thumbnail_generated:
        logger.debug(f"Thumbnail generated: {thumbnail_path}")
    else:
        logger.warning("Thumbnail generation failed")

    relative_path = file_path.relative_to(settings.BASE_DIR)
    relative_thumb = thumbnail_path.relative_to(settings.BASE_DIR) if thumbnail_generated else None

    media = Media(
        filename=unique_filename,
        path=str(relative_path),
        thumbnail_path=str(relative_thumb) if relative_thumb else None,
        hash=file_hash,
        file_type=metadata["file_type"],
        mime_type=metadata["mime_type"],
        file_size=metadata["file_size"],
        width=metadata["width"],
        height=metadata["height"],
        duration=metadata["duration"],
        rating=rating,
        source=source if source else None,
    )

    tag_ids_to_update = []
    if tags:
        tag_list = [t.strip() for t in tags.split() if t.strip()]
        parsed_hints = None
        if category_hints:
            try:
                parsed_hints = json.loads(category_hints)
            except (json.JSONDecodeError, TypeError):
                pass
        media.tags = get_or_create_tags(db, tag_list, category_hints=parsed_hints)
        tag_ids_to_update = [tag.id for tag in media.tags]
        logger.debug(f"Tags added: {tag_list}")

    affected_album_ids = []
    if album_ids:
        try:
            a_ids = [
                int(id_str.strip())
                for id_str in album_ids.split(",")
                if id_str.strip().isdigit()
            ]
            if a_ids:
                albums = db.query(Album).filter(Album.id.in_(a_ids)).all()
                media.albums = albums
                affected_album_ids = [album.id for album in albums]
                logger.debug(f"Added to albums: {affected_album_ids}")
        except Exception as e:
            logger.error(f"Error parsing album_ids: {e}")

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

    logger.info(f"Media saved: ID={media.id}, filename={unique_filename}")

    invalidate_media_cache()
    invalidate_tag_cache()

    return MediaResponse.model_validate(media)

@router.get("/")
@router.get("")
@cache_response(expire=3600, key_prefix="media_list")
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
        logger.error(f"Error in get_media_list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to retrieve media list", e))

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
        logger.error(f"Error in get_media_batch: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to retrieve media batch", e))

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
                if not file_path.is_relative_to(settings.ORIGINAL_DIR.resolve()):
                    raise ValueError("Access denied")
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
            
            logger.info(f"Uploading file: {file.filename} -> {unique_filename}")
            
            with open(file_path, 'wb') as buffer:
                buffer.write(contents)
            
            logger.debug(f"File saved to: {file_path}")
        
        try:
            return process_and_save_media(
                db=db,
                file_path=file_path,
                unique_filename=unique_filename,
                rating=rating,
                tags=tags,
                album_ids=album_ids,
                source=source,
                category_hints=category_hints,
            )
        except HTTPException as e:
            if e.status_code == 409:
                # Duplicate: clean up only if it was a fresh upload (not a scan)
                if not scanned_path and file_path.exists():
                    file_path.unlink(missing_ok=True)
            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading media: {e}", exc_info=True)

        # Clean up files on error (only if it was a new upload, not scanned)
        if not scanned_path:
            if 'file_path' in locals() and file_path.exists():
                file_path.unlink(missing_ok=True)

        raise HTTPException(status_code=500, detail=safe_error_detail("Upload failed", e))

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
        logger.error(f"Failed to cleanup cache for unshared media: {e}")
    
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

ARCHIVE_CHUNKS_DIR = settings.CACHE_DIR / "archive-chunks"
ARCHIVE_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

# Max chunk size: 99MB (CloudFlare compatible)
MAX_CHUNK_SIZE = 99 * 1024 * 1024

def cleanup_archive_chunks(max_age_seconds: int = 0):
    """Remove leftover chunk directories.

    Args:
        max_age_seconds: Only remove directories older than this many seconds.
                         0 means remove everything (used on startup).
    """
    import time

    if not ARCHIVE_CHUNKS_DIR.exists():
        return

    now = time.time()
    for child in ARCHIVE_CHUNKS_DIR.iterdir():
        if child.is_dir():
            if max_age_seconds > 0:
                try:
                    age = now - child.stat().st_mtime
                    if age < max_age_seconds:
                        continue
                except OSError:
                    pass
            shutil.rmtree(child, ignore_errors=True)

@router.post("/archive-chunk")
async def upload_archive_chunk(
    file: UploadFile = File(...),
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
    current_user: User = Depends(require_admin_mode)
):
    """Receive a single chunk of an archive upload."""
    import re

    # Validate upload_id is a UUID to prevent path traversal
    if not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=400, detail="Invalid chunk_index")

    contents = await file.read()
    if len(contents) > MAX_CHUNK_SIZE:
        raise HTTPException(status_code=400, detail=f"Chunk too large (max {MAX_CHUNK_SIZE // (1024 * 1024)}MB)")

    chunk_dir = ARCHIVE_CHUNKS_DIR / upload_id
    chunk_dir.mkdir(parents=True, exist_ok=True)

    # Store metadata on first chunk
    meta_path = chunk_dir / "meta.json"
    if chunk_index == 0:
        import json as _json
        with open(meta_path, 'w') as f:
            _json.dump({"filename": filename, "total_chunks": total_chunks}, f)

    # Write chunk
    chunk_path = chunk_dir / f"chunk_{chunk_index}"
    with open(chunk_path, 'wb') as f:
        f.write(contents)

    return {"received": chunk_index, "total": total_chunks}

@router.post("/extract-archive")
async def extract_archive(
    upload_id: str = Form(...),
    current_user: User = Depends(require_admin_mode)
):
    """Reassemble chunks and extract files from the archive.

    Extracted media files are stored on disk and only metadata is returned.
    Use GET /archive-file/{upload_id}/{file_id} to fetch individual files.
    """
    import mimetypes
    import re
    import tarfile
    import zipfile

    # Validate upload_id
    if not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    chunk_dir = ARCHIVE_CHUNKS_DIR / upload_id
    if not chunk_dir.exists():
        raise HTTPException(status_code=400, detail="No chunks found for this upload_id")

    meta_path = chunk_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=400, detail="Missing upload metadata")

    import json as _json
    with open(meta_path, 'r') as f:
        meta = _json.load(f)

    filename = meta["filename"]
    total_chunks = meta["total_chunks"]

    # Verify all chunks are present
    for i in range(total_chunks):
        if not (chunk_dir / f"chunk_{i}").exists():
            raise HTTPException(status_code=400, detail=f"Missing chunk {i}")

    file_list = []

    try:
        # Use the chunk_dir itself for extraction (persistent, not a tempdir)
        extract_dir = chunk_dir / "extracted"
        extract_dir.mkdir(exist_ok=True)

        archive_path = chunk_dir / filename

        # Reassemble chunks into the archive file
        with open(archive_path, 'wb') as f:
            for i in range(total_chunks):
                chunk_path = chunk_dir / f"chunk_{i}"
                with open(chunk_path, 'rb') as chunk_f:
                    shutil.copyfileobj(chunk_f, f)

        # Delete chunk files now that we have the assembled archive
        for i in range(total_chunks):
            (chunk_dir / f"chunk_{i}").unlink(missing_ok=True)

        # Extract based on file type
        if filename.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    if member.startswith('/') or '..' in member:
                        raise HTTPException(status_code=400, detail="Invalid file path in archive")
                zip_ref.extractall(extract_dir)

        elif filename.endswith(('.tar.gz', '.tgz')):
            with tarfile.open(archive_path, 'r:gz') as tar_ref:
                for member in tar_ref.getmembers():
                    if member.name.startswith('/') or '..' in member.name:
                        raise HTTPException(status_code=400, detail="Invalid file path in archive")
                tar_ref.extractall(extract_dir)
        else:
            raise HTTPException(status_code=400, detail="Unsupported archive format")

        # Delete the reassembled archive to free disk space
        archive_path.unlink(missing_ok=True)

        # Collect metadata for valid extracted files
        valid_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'video/mp4', 'video/webm']
        file_index = 0
        for extracted_file in extract_dir.rglob('*'):
            if extracted_file.is_symlink():
                continue

            if extracted_file.is_file():
                mime_type, _ = mimetypes.guess_type(extracted_file.name)
                if mime_type in valid_types:
                    # Rename to a predictable indexed name for serving
                    ext = extracted_file.suffix
                    indexed_name = f"{file_index}{ext}"
                    target = extract_dir / indexed_name
                    if extracted_file != target:
                        extracted_file.rename(target)

                    file_list.append({
                        'file_id': file_index,
                        'filename': extracted_file.name,
                        'mime_type': mime_type,
                    })
                    file_index += 1

        # Update metadata so cleanup knows this is an extracted session
        with open(meta_path, 'w') as f:
            _json.dump({"filename": filename, "total_chunks": total_chunks, "extracted": True, "file_count": file_index}, f)

        return {
            'upload_id': upload_id,
            'files': file_list,
            'count': len(file_list)
        }

    except zipfile.BadZipFile:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Invalid or corrupted zip file")
    except tarfile.TarError:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Invalid or corrupted tar.gz file")
    except HTTPException:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        logger.exception("Import error occurred")
        raise HTTPException(status_code=400, detail=safe_error_detail("Error extracting archive", e))

@router.get("/archive-file/{upload_id}/{file_id}")
async def get_archive_file(
    upload_id: str,
    file_id: int,
    current_user: User = Depends(require_admin_mode)
):
    """Serve an individual extracted file from an archive session."""
    import re

    if not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    extract_dir = ARCHIVE_CHUNKS_DIR / upload_id / "extracted"
    if not extract_dir.exists():
        raise HTTPException(status_code=404, detail="No extracted files found")

    # Find the file by index (could have various extensions)
    matches = list(extract_dir.glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = matches[0]
    import mimetypes
    mime_type, _ = mimetypes.guess_type(file_path.name)

    return FileResponse(file_path, media_type=mime_type)

@router.delete("/archive-cleanup/{upload_id}")
async def cleanup_archive(
    upload_id: str,
    current_user: User = Depends(require_admin_mode)
):
    """Clean up extracted archive files after the frontend is done with them."""
    import re

    if not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    chunk_dir = ARCHIVE_CHUNKS_DIR / upload_id
    shutil.rmtree(chunk_dir, ignore_errors=True)
    return {"message": "Cleaned up"}

MEDIA_CHUNKS_DIR = settings.CACHE_DIR / "media-chunks"
MEDIA_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

def cleanup_media_chunks(max_age_seconds: int = 0):
    """Remove leftover media-chunk directories.

    Args:
        max_age_seconds: Only remove directories older than this many seconds.
                         0 means remove everything (used on startup).
    """
    import time

    if not MEDIA_CHUNKS_DIR.exists():
        return

    now = time.time()
    for child in MEDIA_CHUNKS_DIR.iterdir():
        if child.is_dir():
            if max_age_seconds > 0:
                try:
                    age = now - child.stat().st_mtime
                    if age < max_age_seconds:
                        continue
                except OSError:
                    pass
            shutil.rmtree(child, ignore_errors=True)

@router.post("/upload-chunk")
async def upload_media_chunk(
    file: UploadFile = File(...),
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
    current_user: User = Depends(require_admin_mode)
):
    """Receive a single chunk of a media upload."""
    import re

    if not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=400, detail="Invalid chunk_index")

    contents = await file.read()
    if len(contents) > MAX_CHUNK_SIZE:
        raise HTTPException(status_code=400, detail=f"Chunk too large (max {MAX_CHUNK_SIZE // (1024 * 1024)}MB)")

    chunk_dir = MEDIA_CHUNKS_DIR / upload_id
    chunk_dir.mkdir(parents=True, exist_ok=True)

    meta_path = chunk_dir / "meta.json"
    if chunk_index == 0:
        import json as _json
        with open(meta_path, 'w') as f:
            _json.dump({"filename": filename, "total_chunks": total_chunks}, f)

    chunk_path = chunk_dir / f"chunk_{chunk_index}"
    with open(chunk_path, 'wb') as f:
        f.write(contents)

    return {"received": chunk_index, "total": total_chunks}

@router.post("/upload-finalize", response_model=MediaResponse)
async def finalize_chunked_upload(
    upload_id: str = Form(...),
    rating: RatingEnum = Form(RatingEnum.safe),
    tags: str = Form(""),
    album_ids: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    category_hints: Optional[str] = Form(None),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Reassemble chunks and process as a regular media upload."""
    import re
    import json as _json

    if not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    chunk_dir = MEDIA_CHUNKS_DIR / upload_id
    if not chunk_dir.exists():
        raise HTTPException(status_code=400, detail="No chunks found for this upload_id")

    meta_path = chunk_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=400, detail="Missing upload metadata")

    with open(meta_path) as f:
        meta = _json.load(f)

    filename = meta["filename"]
    total_chunks = meta["total_chunks"]

    for i in range(total_chunks):
        if not (chunk_dir / f"chunk_{i}").exists():
            raise HTTPException(status_code=400, detail=f"Missing chunk {i}")

    # Reassemble into a single file in ORIGINAL_DIR
    try:
        unique_filename = get_unique_filename(settings.ORIGINAL_DIR, filename)
        file_path = settings.ORIGINAL_DIR / unique_filename

        with open(file_path, 'wb') as out_f:
            for i in range(total_chunks):
                chunk_path = chunk_dir / f"chunk_{i}"
                with open(chunk_path, 'rb') as chunk_f:
                    shutil.copyfileobj(chunk_f, out_f)

        # Clean up chunks immediately
        shutil.rmtree(chunk_dir, ignore_errors=True)

        # Delegate to shared helper
        try:
            return process_and_save_media(
                db=db,
                file_path=file_path,
                unique_filename=unique_filename,
                rating=rating,
                tags=tags,
                album_ids=album_ids,
                source=source,
                category_hints=category_hints,
            )
        except HTTPException as e:
            if e.status_code == 409:
                file_path.unlink(missing_ok=True)
            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chunked upload finalize: {e}", exc_info=True)

        if 'file_path' in locals() and file_path.exists():
            file_path.unlink(missing_ok=True)

        shutil.rmtree(chunk_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=safe_error_detail("Chunked upload failed", e))
