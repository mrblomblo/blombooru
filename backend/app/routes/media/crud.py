from pathlib import Path
from typing import Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, or_
from sqlalchemy.orm import Session, joinedload, selectinload
from ...auth import require_admin_mode
from ...config import settings
from ...database import get_db
from ...enums import RatingEnum
from ...models import Media, User
from ...schemas import (
    MediaCreatedResponse,
    MediaDetailResponse,
    MediaReorderRequest,
    MediaResponse,
    MediaUpdate,
)
from ...utils.album_utils import handle_media_deleted, handle_media_rating_changed
from ...utils.cache import invalidate_media_cache, invalidate_media_item_cache, invalidate_tag_cache
from ...utils.format_registry import format_registry
from ...utils.logger import logger
from ...utils.media_helpers import (
    delete_media_cache,
    extract_media_metadata,
    get_unique_filename,
    serve_media_file,
)
from ...utils.media_relations import next_child_sort_position
from ...utils.request_helpers import safe_error_detail
from ...utils.tag_utils import get_escalated_rating, get_newly_added_tags
from ...utils.thumbnail_generator import thumbnail_mime_type
from .ingestion import process_and_save_media, sync_description_enlarged
from .tags import apply_media_tag_implications, resolve_media_tag_update, update_tag_counts

router = APIRouter()

class DescriptionPreviewRequest(BaseModel):
    text: str = Field("", max_length=50000)

class DescriptionPreviewResponse(BaseModel):
    html: str

@router.post("/preview-description", response_model=DescriptionPreviewResponse)
async def preview_media_description(
    req: DescriptionPreviewRequest,
    current_user: User = Depends(require_admin_mode),
):
    """Render a draft media description as Markdown (admin only)."""
    from ...utils.markdown import render_description_markdown
    return DescriptionPreviewResponse(html=render_description_markdown(req.text))

@router.get("/{media_id}")
async def get_media(media_id: int, db: Session = Depends(get_db)):
    """Get media by ID"""
    media = db.query(Media).options(joinedload(Media.tags), selectinload(Media.media_tag_links)).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    result = MediaDetailResponse.model_validate(media).model_dump()
    result['share_ai_metadata'] = media.share_ai_metadata if hasattr(media, 'share_ai_metadata') else False
    
    # Add parent and siblings info
    hierarchy = []
    if media.parent_id:
        # I am a child
        related = (
            db.query(Media)
            .options(selectinload(Media.tags), selectinload(Media.media_tag_links))
            .filter(
                or_(
                    Media.id == media.parent_id,
                    and_(Media.parent_id == media.parent_id, Media.id != media.id)
                )
            )
            .order_by(
                case((Media.id == media.parent_id, 0), else_=1).asc(),
                Media.parent_sort_position.asc().nulls_last(),
                Media.id.asc(),
            )
            .all()
        )
        hierarchy = [MediaResponse.model_validate(r).model_dump() for r in related]
    else:
        # I might be a parent
        children = (
            db.query(Media)
            .options(selectinload(Media.tags), selectinload(Media.media_tag_links))
            .filter(Media.parent_id == media.id)
            .order_by(Media.parent_sort_position.asc().nulls_last(), Media.id.asc())
            .all()
        )
        hierarchy = [MediaResponse.model_validate(c).model_dump() for c in children]
    
    result['hierarchy'] = hierarchy
    return result

@router.get("/{media_id}/file")
async def get_media_file(media_id: int, chunked: bool = False, download: bool = False):
    """Serve media file. When download is requested or no transcoded version exists, serve original file."""
    db = next(get_db())
    try:
        media = db.query(Media).filter(Media.id == media_id).first()
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
        
        # If download is requested or no transcoded version exists, serve original
        if download or not media.transcoded_path:
            file_path = settings.BASE_DIR / media.path
            mime_type = media.mime_type
        else:
            file_path = settings.BASE_DIR / media.transcoded_path
            if not file_path.exists():
                file_path = settings.BASE_DIR / media.path
                mime_type = media.mime_type
            else:
                mime_type = format_registry.get_mime_type(file_path.name, default=media.mime_type)
        
        filename = media.filename if download else None
    finally:
        db.close()

    return await serve_media_file(file_path, mime_type, chunked=chunked, download=download, filename=filename)

@router.get("/{media_id}/thumbnail")
async def get_media_thumbnail(media_id: int):
    """Serve thumbnail"""
    db = next(get_db())
    try:
        media = db.query(Media).filter(Media.id == media_id).first()
        if not media or not media.thumbnail_path:
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        thumb_path = settings.BASE_DIR / media.thumbnail_path
    finally:
        db.close()

    return await serve_media_file(thumb_path, thumbnail_mime_type(thumb_path), "Thumbnail file not found")

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
    
    return extract_media_metadata(file_path)

@router.post("/", response_model=MediaCreatedResponse)
async def upload_media(
    file: UploadFile = File(None),
    scanned_path: Optional[str] = Form(None),
    rating: RatingEnum = Form(RatingEnum.safe),
    tags: str = Form(""),
    album_ids: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    category_hints: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    custom_date: Optional[str] = Form(None),
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
            
            # file_hash is calculated inside process_and_save_media
            unique_filename = file_path.name  # Keep original name
            
        else:
            # REGULAR UPLOAD
            if not file:
                raise HTTPException(status_code=400, detail="Either file or scanned_path is required")
            
            contents = await file.read()
            
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
                description=description,
                explicit_date=custom_date,
            )
        except HTTPException as e:
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

@router.patch("/{media_id}", response_model=MediaDetailResponse)
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
    
    rating_changed = False
    if updates.rating:
        if media.rating != updates.rating:
            media.rating = updates.rating
            rating_changed = True
    
    if 'source' in updates.model_fields_set:
        media.source = updates.source if updates.source else None
    
    if 'description' in updates.model_fields_set:
        media.description = updates.description if updates.description else None
    
    if 'description_enlarged' in updates.model_fields_set and updates.description_enlarged is not None:
        media.description_enlarged = updates.description_enlarged

    sync_description_enlarged(media)

    custom_date_changed = False
    if 'custom_date' in updates.model_fields_set:
        old_custom_date = media.custom_date
        if updates.custom_date is None or str(updates.custom_date).strip() == "":
            media.custom_date = media.uploaded_at
        else:
            from ...utils.date_extractor import parse_explicit_custom_date
            parsed = parse_explicit_custom_date(updates.custom_date)
            if parsed is None:
                raise HTTPException(status_code=422, detail="Invalid custom_date format")
            media.custom_date = parsed
        if old_custom_date != media.custom_date:
            custom_date_changed = True
    
    affected_tag_ids = []
    implied_by_tag_id_update: Optional[dict[int, list[list[str]]]] = None
    if updates.tags is not None:
        old_tag_ids = [tag.id for tag in media.tags]
        previous_tags = list(media.tags)
        tags_list, implied_by_tag_id_update = resolve_media_tag_update(
            db,
            media.id,
            updates.tags,
            client_implied_tags=updates.implied_tags,
        )
        media.tags = tags_list
        new_tag_ids = [tag.id for tag in media.tags]
        affected_tag_ids = list(set(old_tag_ids + new_tag_ids))
        added_tags = [] if updates.rating else get_newly_added_tags(previous_tags, media.tags)
        escalated = get_escalated_rating(media.rating, added_tags)
        if escalated and media.rating != escalated:
            media.rating = escalated
            rating_changed = True

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
                media.parent_sort_position = next_child_sort_position(db, updates.parent_id)
                media.parent_id = updates.parent_id
        else:
            if media.parent_id is not None:
                parent_id_changed = True
            media.parent_id = None
            media.parent_sort_position = None
    
    db.flush()
    if implied_by_tag_id_update is not None:
        apply_media_tag_implications(db, media, implied_by_tag_id_update)
    db.commit()

    if rating_changed:
        handle_media_rating_changed(db, media_id, media.rating.value if hasattr(media.rating, "value") else media.rating)

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

        if custom_date_changed:
            invalidate_media_cache()
    else:
        invalidate_media_cache()
        invalidate_tag_cache()
    
    return MediaDetailResponse.model_validate(media)

@router.put("/{media_id}/children/reorder")
async def reorder_media_children(
    media_id: int,
    data: MediaReorderRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Set manual sort positions for children of a media item."""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    ordered_ids = list(dict.fromkeys(data.media_ids))
    existing_children = (
        db.query(Media)
        .filter(Media.parent_id == media_id)
        .order_by(Media.parent_sort_position.asc().nulls_last(), Media.id.asc())
        .all()
    )
    children_by_id = {c.id: c for c in existing_children}

    pos = 0
    updated_ids = set()
    for child_id in ordered_ids:
        child = children_by_id.get(child_id)
        if child is not None:
            child.parent_sort_position = pos
            pos += 1
            updated_ids.add(child_id)

    for child in existing_children:
        if child.id not in updated_ids:
            child.parent_sort_position = pos
            pos += 1

    db.commit()
    invalidate_media_cache(rebuild_similarity=False)
    return {"message": "Child media order updated"}

@router.delete("/{media_id}/children/reorder")
async def clear_media_children_order(
    media_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Clear manual sort order for children of a media item."""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    db.query(Media).filter(Media.parent_id == media_id).update(
        {Media.parent_sort_position: None},
        synchronize_session=False,
    )
    db.commit()
    invalidate_media_cache(rebuild_similarity=False)
    return {"message": "Manual child media order cleared"}

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
    delete_media_cache(media)
    file_path.unlink(missing_ok=True)

    if media.transcoded_path:
        transcoded_file_path = settings.BASE_DIR / media.transcoded_path
        transcoded_file_path.unlink(missing_ok=True)
    
    if media.thumbnail_path:
        thumb_path = settings.BASE_DIR / media.thumbnail_path
        thumb_path.unlink(missing_ok=True)
    
    handle_media_deleted(db, [media_id])
    db.query(Media).filter(Media.parent_id == media_id).update(
        {Media.parent_sort_position: None},
        synchronize_session=False,
    )
    db.delete(media)
    db.commit()
    
    if tag_ids:
        update_tag_counts(db, tag_ids)
        db.commit()

    invalidate_media_cache()
    invalidate_tag_cache()
    
    return {"message": "Media deleted successfully"}
