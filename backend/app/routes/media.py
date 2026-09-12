import json
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                     HTTPException, Query, Request, UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from ..auth import require_admin_mode
from ..config import settings
from ..utils.request_helpers import safe_error_detail
from ..database import get_db
from ..models import (Album, Media, Tag, User, blombooru_album_media,
                      blombooru_media_tags)
from ..schemas import (AlbumListResponse, BatchMediaRequest, BatchMetadataRequest,
                       BulkTagUpdateRequest, BulkTagUpdateResponse, MediaCreate,
                       MediaResponse, MediaUpdate, RatingEnum, ShareSettingsUpdate)
from ..utils.album_utils import (get_bulk_album_metrics, get_flattened_media_ids,
                                update_album_last_modified)
from ..utils.cache import (cache_response, invalidate_album_cache,
                           invalidate_media_cache, invalidate_media_item_cache,
                           invalidate_tag_cache)
from ..utils.format_registry import format_registry
from ..utils.logger import logger
from ..utils.media_helpers import (create_stripped_media_cache,
                                   delete_media_cache, extract_media_metadata,
                                   get_unique_filename, sanitize_filename,
                                   serve_media_file)
from ..utils.media_processor import calculate_file_hash, process_media_file
from ..utils.media_sort import apply_media_sort
from ..utils.search_parser import (apply_custom_filters_or,
                                   apply_search_criteria, parse_search_query)
from ..utils.thumbnail_generator import generate_thumbnail
from ..utils.transcoder import (get_transcoded_path_for_original,
                                transcode_media_if_needed)

router = APIRouter(prefix="/api/media", tags=["media"])

# Maximum number of IDs per SQL IN-clause to avoid parameter limits
BATCH_CHUNK_SIZE = 500

class PostUpdateRequest(BaseModel):
    """Request body for the Update Post (from-source) endpoint.

    Controls which fields are overwritten and how. Defaults to the least destructive option.
    """
    update_tags: bool = False
    tags: Optional[list[str]] = None
    merge_tags: bool = True          # True = merge (add new, keep old); False = replace (remove old, set new)
    category_hints: Optional[dict[str, str]] = None
    update_rating: bool = False
    rating: Optional[str] = None
    update_source: bool = False
    source: Optional[str] = None
    update_description: bool = False
    description: Optional[str] = None
    update_filename: bool = False
    filename: Optional[str] = None
    update_file: bool = False
    file_url: Optional[str] = None

@router.patch("/{media_id}/update-from-source", response_model=MediaResponse)
async def update_from_source(
    media_id: int,
    req: PostUpdateRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Update an existing post's metadata and/or media file.

    Supports selective overwriting: callers set update_* flags for only the
    fields they want changed.
    """
    media = db.query(Media).options(joinedload(Media.tags)).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    affected_tag_ids: list[int] = []

    if req.update_tags and req.tags is not None:
        old_tag_ids = [tag.id for tag in media.tags]

        if req.merge_tags:
            # Merge: keep existing tags, add any that are missing
            existing_names = {tag.name.lower() for tag in media.tags}
            new_names = [t for t in req.tags if t.strip().lower() not in existing_names]
            if new_names:
                new_tags = get_or_create_tags(db, new_names, category_hints=req.category_hints)
                media.tags = list(media.tags) + new_tags
        else:
            # Replace: remove all current tags and set the new list
            media.tags = get_or_create_tags(db, req.tags, category_hints=req.category_hints)

        new_tag_ids = [tag.id for tag in media.tags]
        affected_tag_ids = list(set(old_tag_ids + new_tag_ids))

    if req.update_rating and req.rating:
        media.rating = req.rating

    if req.update_source:
        media.source = req.source or None

    if req.update_description:
        media.description = req.description or None

    if req.update_filename and req.filename:
        new_filename = sanitize_filename(req.filename)
        if new_filename and new_filename != media.filename:
            old_path = settings.BASE_DIR / media.path
            new_unique = get_unique_filename(settings.ORIGINAL_DIR, new_filename)
            new_path = settings.ORIGINAL_DIR / new_unique

            if old_path.exists():
                old_path.rename(new_path)

            # Handle transcoded file rename/move if needed
            fmt = format_registry.get_format(new_unique)
            if fmt and fmt.requires_transcode:
                new_transc_path = get_transcoded_path_for_original(new_path, fmt.transcode_target)
                if media.transcoded_path:
                    old_transc_path = settings.BASE_DIR / media.transcoded_path
                    if old_transc_path.exists():
                        delete_media_cache(old_transc_path)
                        new_transc_path.parent.mkdir(parents=True, exist_ok=True)
                        old_transc_path.rename(new_transc_path)
                        media.transcoded_path = str(new_transc_path.relative_to(settings.BASE_DIR))
                    else:
                        trans_file = transcode_media_if_needed(new_path)
                        media.transcoded_path = str(trans_file.relative_to(settings.BASE_DIR)) if trans_file else None
                else:
                    trans_file = transcode_media_if_needed(new_path)
                    media.transcoded_path = str(trans_file.relative_to(settings.BASE_DIR)) if trans_file else None
            else:
                if media.transcoded_path:
                    old_transc_path = settings.BASE_DIR / media.transcoded_path
                    if old_transc_path.exists():
                        delete_media_cache(old_transc_path)
                        old_transc_path.unlink(missing_ok=True)
                    media.transcoded_path = None

            if media.thumbnail_path:
                old_thumb = settings.BASE_DIR / media.thumbnail_path
                new_thumb_name = Path(new_unique).stem + ".jpg"
                new_thumb = settings.THUMBNAIL_DIR / new_thumb_name
                if old_thumb.exists():
                    old_thumb.rename(new_thumb)
                media.thumbnail_path = str(new_thumb.relative_to(settings.BASE_DIR))

            media.filename = new_unique
            media.path = str(new_path.relative_to(settings.BASE_DIR))

    if req.update_file:
        if not req.file_url:
            raise HTTPException(status_code=400, detail="file_url is required when update_file is true")

        import requests as _requests
        try:
            headers = {"User-Agent": "Blombooru/1.0 (booru-import)"}
            dl = _requests.get(req.file_url, headers=headers, timeout=60, stream=True)
            dl.raise_for_status()
        except _requests.HTTPError as e:
            raise HTTPException(status_code=502, detail=safe_error_detail("Failed to download replacement file", e))
        except _requests.RequestException as e:
            raise HTTPException(status_code=502, detail=safe_error_detail("Failed to download replacement file", e))

        suffix = Path(req.file_url.split("?")[0]).suffix or ".bin"
        import tempfile
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in dl.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                tmp_path = Path(tmp.name)

            new_hash = calculate_file_hash(tmp_path)

            if new_hash == media.hash:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(status_code=409, detail="The replacement file is identical to the current file")

            duplicate = db.query(Media).filter(Media.hash == new_hash, Media.id != media_id).first()
            if duplicate:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(status_code=409, detail=f"Media already exists (duplicate of {duplicate.filename})")

            old_file = settings.BASE_DIR / media.path
            delete_media_cache(old_file)
            old_file.unlink(missing_ok=True)

            if media.transcoded_path:
                old_transc = settings.BASE_DIR / media.transcoded_path
                delete_media_cache(old_transc)
                old_transc.unlink(missing_ok=True)
                media.transcoded_path = None

            shutil.move(str(tmp_path), str(old_file))
            tmp_path = None

            new_meta = process_media_file(old_file, precalculated_hash=new_hash)

            # Regenerate thumbnail
            if media.thumbnail_path:
                old_thumb = settings.BASE_DIR / media.thumbnail_path
                old_thumb.unlink(missing_ok=True)

            thumb_name = Path(media.filename).stem + ".jpg"
            thumb_path = settings.THUMBNAIL_DIR / thumb_name
            thumb_source = (settings.BASE_DIR / new_meta["transcoded_path"]) if new_meta.get("transcoded_path") else old_file
            generate_thumbnail(thumb_source, thumb_path, new_meta["file_type"])
            media.thumbnail_path = str(thumb_path.relative_to(settings.BASE_DIR)) if thumb_path.exists() else None

            media.hash = new_hash
            media.transcoded_path = new_meta.get("transcoded_path")
            media.file_type = new_meta["file_type"]
            media.mime_type = new_meta["mime_type"]
            media.file_size = new_meta["file_size"]
            media.width = new_meta["width"]
            media.height = new_meta["height"]
            media.duration = new_meta["duration"]

        except HTTPException:
            raise
        except Exception as e:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            logger.exception("Error replacing media file")
            raise HTTPException(status_code=500, detail=safe_error_detail("File replacement failed", e))

    db.commit()

    if affected_tag_ids:
        update_tag_counts(db, affected_tag_ids)
        db.commit()

    db.refresh(media)
    invalidate_media_cache()
    invalidate_media_item_cache(media_id)
    invalidate_tag_cache()

    return MediaResponse.model_validate(media)

@router.post("/{media_id}/update-file-finalize", response_model=MediaResponse)
async def update_file_finalize(
    media_id: int,
    upload_id: str = Form(...),
    update_filename: bool = Form(False),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Reassemble a previously chunked device-file upload and replace the stored media.

    Chunks must have been uploaded via POST /api/media/upload-chunk beforehand.
    This endpoint mirrors the logic of upload-finalize but replaces an existing
    media record rather than creating a new one.
    """
    import re
    import json as _json

    if not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    media = db.query(Media).options(joinedload(Media.tags)).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

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

    # Reassemble into a temporary location, then swap
    try:
        tmp_assembled = chunk_dir / "assembled_file"
        with open(tmp_assembled, "wb") as out_f:
            for i in range(total_chunks):
                with open(chunk_dir / f"chunk_{i}", "rb") as chunk_f:
                    shutil.copyfileobj(chunk_f, out_f)

        new_hash = calculate_file_hash(tmp_assembled)

        if new_hash == media.hash:
            shutil.rmtree(chunk_dir, ignore_errors=True)
            raise HTTPException(status_code=409, detail="The replacement file is identical to the current file")

        duplicate = db.query(Media).filter(Media.hash == new_hash, Media.id != media_id).first()
        if duplicate:
            shutil.rmtree(chunk_dir, ignore_errors=True)
            raise HTTPException(status_code=409, detail=f"Media already exists (duplicate of {duplicate.filename})")

        # Determine target filename and path
        if update_filename:
            sanitized = sanitize_filename(filename)
            if not sanitized:
                sanitized = filename
            if sanitized == media.filename:
                target_filename = media.filename
            else:
                target_filename = get_unique_filename(settings.ORIGINAL_DIR, sanitized)
        else:
            new_suffix = Path(filename).suffix.lower()
            old_suffix = Path(media.filename).suffix.lower()
            if new_suffix and new_suffix != old_suffix:
                stem = Path(media.filename).stem
                target_filename = get_unique_filename(settings.ORIGINAL_DIR, f"{stem}{new_suffix}")
            else:
                target_filename = media.filename

        target_file = settings.ORIGINAL_DIR / target_filename
        old_file = settings.BASE_DIR / media.path

        if old_file.exists():
            delete_media_cache(old_file)
            old_file.unlink(missing_ok=True)

        if media.transcoded_path:
            old_transc = settings.BASE_DIR / media.transcoded_path
            delete_media_cache(old_transc)
            old_transc.unlink(missing_ok=True)
            media.transcoded_path = None

        shutil.move(str(tmp_assembled), str(target_file))

        shutil.rmtree(chunk_dir, ignore_errors=True)

        new_meta = process_media_file(target_file, precalculated_hash=new_hash)

        # Regenerate thumbnail
        if media.thumbnail_path:
            old_thumb = settings.BASE_DIR / media.thumbnail_path
            old_thumb.unlink(missing_ok=True)

        thumb_name = Path(target_filename).stem + ".jpg"
        thumb_path = settings.THUMBNAIL_DIR / thumb_name
        thumb_source = (settings.BASE_DIR / new_meta["transcoded_path"]) if new_meta.get("transcoded_path") else target_file
        generate_thumbnail(thumb_source, thumb_path, new_meta["file_type"])
        media.thumbnail_path = str(thumb_path.relative_to(settings.BASE_DIR)) if thumb_path.exists() else None

        media.filename = target_filename
        media.path = str(target_file.relative_to(settings.BASE_DIR))
        media.hash = new_hash
        media.transcoded_path = new_meta.get("transcoded_path")
        media.file_type = new_meta["file_type"]
        media.mime_type = new_meta["mime_type"]
        media.file_size = new_meta["file_size"]
        media.width = new_meta["width"]
        media.height = new_meta["height"]
        media.duration = new_meta["duration"]

        db.commit()
        db.refresh(media)
        invalidate_media_cache()
        invalidate_media_item_cache(media_id)

        return MediaResponse.model_validate(media)

    except HTTPException:
        raise
    except Exception as e:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        logger.exception("Error in update-file-finalize")
        raise HTTPException(status_code=500, detail=safe_error_detail("File update failed", e))

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

def preview_or_create_tags(
    db: Session,
    tag_names: List[str],
    category_hints: Optional[dict] = None,
    expand: bool = True,
    dry_run: bool = False
):
    """Get or create tags by name (or preview them without creating if dry_run=True).
    Resolves aliases and applies tag implications.

    Args:
        db: Database session
        tag_names: List of tag name strings
        category_hints: Optional dict mapping tag names to category strings
                       (e.g. {"artist_name": "artist", "char_name": "character"}).
                       When a tag doesn't exist and a hint is provided, the tag
                       is created with that category instead of the default "general".
        expand: Whether to recursively expand tag implications. Defaults to True.
        dry_run: When True, do not create new Tag rows in the database;
                 instead return proposed tag objects with is_new boolean.
    """
    from ..models import TagAlias
    from ..utils.tag_utils import expand_implications, resolve_aliases

    # Deduplicate input names
    seen_names: set[str] = set()
    unique_names: list[str] = []
    for name in tag_names:
        name = name.strip().lower()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        unique_names.append(name)

    alias_map = resolve_aliases(db, unique_names)

    if not dry_run:
        tag_set: dict[int, Tag] = {}

        for name in unique_names:
            if name in alias_map:
                alias = db.query(TagAlias).filter(TagAlias.alias_name == name).first()
                tag = alias.target_tag if alias else None
            else:
                tag = db.query(Tag).filter(Tag.name == name).first()
                if not tag:
                    category = "general"
                    if category_hints and name in category_hints:
                        category = category_hints[name]
                    tag = Tag(name=name, post_count=0, category=category)
                    db.add(tag)
                    db.flush()

            if tag and tag.id not in tag_set:
                tag_set[tag.id] = tag

        if expand:
            expand_implications(db, tag_set)

        return list(tag_set.values())

    # Dry run
    import fnmatch
    from sqlalchemy import select
    from ..models import TagImplication
    from ..schemas import ProposedTag

    tag_set: dict[int, Tag] = {}
    new_tags: list[ProposedTag] = []
    seen_canonical: set[str] = set()

    for name in unique_names:
        if name in alias_map:
            canonical_name, canonical_category = alias_map[name]
            if canonical_name in seen_canonical:
                continue
            seen_canonical.add(canonical_name)
            tag = db.query(Tag).filter(Tag.name == canonical_name).first()
            if tag:
                tag_set[tag.id] = tag
        else:
            if name in seen_canonical:
                continue
            seen_canonical.add(name)
            tag = db.query(Tag).filter(Tag.name == name).first()
            if tag:
                tag_set[tag.id] = tag
            else:
                category = "general"
                if category_hints and name in category_hints:
                    category = category_hints[name]
                new_tags.append(ProposedTag(
                    name=name,
                    category=category,
                    is_new=True,
                    source="user"
                ))

    if expand:
        expand_implications(db, tag_set)
        pattern_only_implications = db.execute(
            select(TagImplication)
            .where(
                TagImplication.target_tag_patterns.is_not(None),
                ~TagImplication.target_tags.any(),
            )
            .options(selectinload(TagImplication.implied_tags))
        ).scalars().all()
        for imp in pattern_only_implications:
            if imp.target_tag_patterns:
                for n_tag in new_tags:
                    if any(fnmatch.fnmatch(n_tag.name, pat) for pat in imp.target_tag_patterns):
                        for implied in imp.implied_tags:
                            if implied.id not in tag_set:
                                tag_set[implied.id] = implied

    result: list[ProposedTag] = []
    for tag in tag_set.values():
        result.append(ProposedTag(
            name=tag.name,
            category=tag.category,
            is_new=False,
            source="user"
        ))
    for n_tag in new_tags:
        if not any(r.name == n_tag.name for r in result):
            result.append(n_tag)

    return result

def get_or_create_tags(db: Session, tag_names: List[str], category_hints: Optional[dict] = None, expand: bool = True) -> List[Tag]:
    """Get or create tags by name, resolving aliases and applying implications."""
    return preview_or_create_tags(db, tag_names, category_hints=category_hints, expand=expand, dry_run=False)

def process_and_save_media(
    db: Session,
    file_path: Path,
    unique_filename: str,
    rating,
    tags: str,
    album_ids: Optional[str],
    source: Optional[str],
    category_hints: Optional[str],
    description: Optional[str] = None,
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

    metadata = process_media_file(file_path, precalculated_hash=file_hash)
    logger.debug(f"Media processed: {metadata}")

    thumbnail_filename = Path(unique_filename).stem + ".jpg"
    thumbnail_path = settings.THUMBNAIL_DIR / thumbnail_filename

    logger.debug(f"Generating thumbnail: {thumbnail_filename}")
    thumb_source = (settings.BASE_DIR / metadata["transcoded_path"]) if metadata.get("transcoded_path") else file_path
    thumbnail_generated = generate_thumbnail(thumb_source, thumbnail_path, metadata["file_type"])

    if thumbnail_generated:
        logger.debug(f"Thumbnail generated: {thumbnail_path}")
    else:
        logger.warning("Thumbnail generation failed")

    relative_path = file_path.relative_to(settings.BASE_DIR)
    relative_thumb = thumbnail_path.relative_to(settings.BASE_DIR) if thumbnail_generated else None

    media = Media(
        filename=unique_filename,
        path=str(relative_path),
        transcoded_path=metadata.get("transcoded_path"),
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
        description=description if description else None,
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
    custom_filter: Optional[List[str]] = Query(default=None),
    sort: Optional[str] = None,
    order: Optional[str] = None,
    seed: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Get paginated media list"""
    if limit is None or not isinstance(limit, int):
        limit = settings.get_items_per_page()
    
    try:
        query = db.query(Media).options(selectinload(Media.tags))
        
        if rating:
            ratings_list = [r.strip().lower() for r in rating.split(",") if r.strip()]
            valid_ratings = [RatingEnum[r] for r in ratings_list if r in RatingEnum.__members__]
            if valid_ratings:
                query = query.filter(Media.rating.in_(valid_ratings))

        if custom_filter:
            query = apply_custom_filters_or(query, custom_filter, db)
        
        # Sorting
        sort_by = sort if sort else settings.get_default_sort()
        sort_order = order if order else settings.get_default_order()
        query = apply_media_sort(query, sort_by, sort_order, db, seed)
        
        # Pagination
        offset = (page - 1) * limit
        
        from sqlalchemy import func
        query = query.add_columns(func.count(Media.id).over().label('total_count'))
        
        results = query.offset(offset).limit(limit).all()
        
        if results:
            total = results[0].total_count
            media_list = [r[0] for r in results]
        else:
            total = 0
            media_list = []
        
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

def _fetch_media_batch_tags_only(db: Session, media_ids: List[int], include_metadata: bool = False) -> List[dict]:
    """Fast projection query returning only id, filename, file_type, tags (name, category), and optional metadata."""
    results = []
    
    for i in range(0, len(media_ids), BATCH_CHUNK_SIZE):
        chunk_ids = media_ids[i:i + BATCH_CHUNK_SIZE]
        query_cols = [
            Media.id,
            Media.filename,
            Media.file_type,
            Tag.name,
            Tag.category,
        ]
        if include_metadata:
            query_cols.append(Media.path)

        query = (
            db.query(*query_cols)
            .filter(Media.id.in_(chunk_ids))
            .outerjoin(blombooru_media_tags, Media.id == blombooru_media_tags.c.media_id)
            .outerjoin(Tag, blombooru_media_tags.c.tag_id == Tag.id)
            .order_by(Media.id)
        )
        rows = query.all()
        media_map = {}
        for row in rows:
            m_id = row[0]
            filename = row[1]
            file_type = row[2]
            tag_name = row[3]
            tag_cat = row[4]
            rel_path = row[5] if include_metadata else None

            if m_id not in media_map:
                ft_val = file_type.value if hasattr(file_type, 'value') else file_type
                item_dict = {
                    "id": m_id,
                    "filename": filename,
                    "file_type": ft_val,
                    "tags": []
                }
                if include_metadata:
                    meta = None
                    if rel_path:
                        fpath = settings.BASE_DIR / rel_path
                        if fpath.exists():
                            try:
                                meta = extract_media_metadata(fpath)
                            except Exception:
                                pass
                    item_dict["metadata"] = meta
                media_map[m_id] = item_dict

            if tag_name:
                cat_val = tag_cat.value if hasattr(tag_cat, 'value') else tag_cat
                media_map[m_id]["tags"].append({
                    "name": tag_name,
                    "category": cat_val
                })

        for m_id in chunk_ids:
            if m_id in media_map:
                results.append(media_map[m_id])
    return results

def _fetch_media_batch_full(db: Session, media_ids: List[int]) -> List[dict]:
    """Full MediaResponse batch serialization in chunks to respect parameter limits."""
    results = []
    for i in range(0, len(media_ids), BATCH_CHUNK_SIZE):
        chunk_ids = media_ids[i:i + BATCH_CHUNK_SIZE]
        media_list = db.query(Media).options(selectinload(Media.tags)).filter(Media.id.in_(chunk_ids)).all()
        media_dict = {m.id: m for m in media_list}
        for m_id in chunk_ids:
            if m_id in media_dict:
                results.append(MediaResponse.model_validate(media_dict[m_id]))
    return results

@router.get("/batch")
async def get_media_batch(
    ids: str = Query(..., description="Comma-separated list of media IDs"),
    projection: Optional[str] = Query(None, description="Optional projection, e.g. 'tags_only' or 'ai_metadata'"),
    db: Session = Depends(get_db)
):
    """Get multiple media items by their IDs in a single request"""
    try:
        media_ids = [int(id_str.strip()) for id_str in ids.split(",") if id_str.strip().isdigit()]
        if not media_ids:
            return {"items": []}
            
        if projection == "tags_only":
            items = _fetch_media_batch_tags_only(db, media_ids, include_metadata=False)
        elif projection in ("ai_metadata", "tags_and_metadata"):
            items = _fetch_media_batch_tags_only(db, media_ids, include_metadata=True)
        else:
            items = _fetch_media_batch_full(db, media_ids)
            
        return {"items": items}
    except Exception as e:
        logger.error(f"Error in get_media_batch: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to retrieve media batch", e))

@router.post("/batch")
async def post_media_batch(
    payload: BatchMediaRequest,
    db: Session = Depends(get_db)
):
    """Get multiple media items by their IDs via POST body."""
    try:
        if not payload.ids:
            return {"items": []}
            
        if payload.projection == "tags_only":
            items = _fetch_media_batch_tags_only(db, payload.ids, include_metadata=False)
        elif payload.projection in ("ai_metadata", "tags_and_metadata"):
            items = _fetch_media_batch_tags_only(db, payload.ids, include_metadata=True)
        else:
            items = _fetch_media_batch_full(db, payload.ids)
            
        return {"items": items}
    except Exception as e:
        logger.error(f"Error in post_media_batch: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to retrieve media batch", e))

@router.post("/batch-metadata")
async def post_media_batch_metadata(
    payload: BatchMetadataRequest,
    db: Session = Depends(get_db)
):
    """Get metadata for multiple media items by their IDs."""
    try:
        if not payload.ids:
            return {"items": {}}

        results = {}
        for i in range(0, len(payload.ids), BATCH_CHUNK_SIZE):
            chunk = payload.ids[i:i + BATCH_CHUNK_SIZE]
            rows = db.query(Media.id, Media.path).filter(Media.id.in_(chunk)).all()
            for mid, rel_path in rows:
                if rel_path:
                    file_path = settings.BASE_DIR / rel_path
                    if file_path.exists():
                        try:
                            meta = extract_media_metadata(file_path)
                            if meta:
                                results[str(mid)] = meta
                        except Exception:
                            pass
        return {"items": results}
    except Exception as e:
        logger.error(f"Error in post_media_batch_metadata: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to retrieve media metadata batch", e))

@router.post("/bulk-update-tags", response_model=BulkTagUpdateResponse)
async def bulk_update_tags(
    payload: BulkTagUpdateRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Atomically update tags across multiple media items with pre-validation and conflict-safe tag creation."""
    if not payload.items:
        return BulkTagUpdateResponse(status="success", updated_count=0, updated_media_ids=[])

    # 1. Pre-validation
    requested_ids = [item.id for item in payload.items]
    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(status_code=400, detail="Duplicate media IDs in update request")

    existing_media_ids = set()
    for i in range(0, len(requested_ids), BATCH_CHUNK_SIZE):
        chunk = requested_ids[i:i + BATCH_CHUNK_SIZE]
        found_ids = [r[0] for r in db.query(Media.id).filter(Media.id.in_(chunk)).all()]
        existing_media_ids.update(found_ids)

    missing_ids = set(requested_ids) - existing_media_ids
    if missing_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Media items not found: {sorted(list(missing_ids))[:10]}"
        )

    for item in payload.items:
        for tag in item.tags:
            if not isinstance(tag, str) or not tag.strip():
                raise HTTPException(status_code=400, detail=f"Invalid empty tag name for media ID {item.id}")
            if len(tag.strip()) > 255:
                raise HTTPException(status_code=400, detail=f"Tag name exceeds 255 characters: {tag[:30]}...")

    # 2. Collect unique tag names across entire batch and resolve aliases
    from ..utils.tag_utils import resolve_aliases, expand_implications
    from ..models import TagAlias

    all_raw_tags = set()
    for item in payload.items:
        for tag in item.tags:
            norm = tag.strip().lower()
            if norm:
                all_raw_tags.add(norm)

    alias_map = resolve_aliases(db, list(all_raw_tags))

    resolved_unique_names = set()
    for name in all_raw_tags:
        if name in alias_map:
            resolved_unique_names.add(alias_map[name][0].lower())
        else:
            resolved_unique_names.add(name)

    # 3. Concurrency-safe / upsert tag creation
    existing_tags_map = {}
    resolved_list = list(resolved_unique_names)
    for i in range(0, len(resolved_list), BATCH_CHUNK_SIZE):
        chunk = resolved_list[i:i + BATCH_CHUNK_SIZE]
        tags = db.query(Tag).filter(Tag.name.in_(chunk)).all()
        for t in tags:
            existing_tags_map[t.name.lower()] = t

    missing_tag_names = [n for n in resolved_unique_names if n not in existing_tags_map]

    if missing_tag_names:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(Tag).values([
            {"name": name, "category": "general", "post_count": 0}
            for name in missing_tag_names
        ]).on_conflict_do_nothing(index_elements=["name"])
        db.execute(stmt)
        db.flush()

        # Re-query all resolved tags to ensure complete map
        for i in range(0, len(resolved_list), BATCH_CHUNK_SIZE):
            chunk = resolved_list[i:i + BATCH_CHUNK_SIZE]
            tags = db.query(Tag).filter(Tag.name.in_(chunk)).all()
            for t in tags:
                existing_tags_map[t.name.lower()] = t

    # 4. Fetch old tags to compute affected tag IDs
    old_tag_ids = set()
    for i in range(0, len(requested_ids), BATCH_CHUNK_SIZE):
        chunk = requested_ids[i:i + BATCH_CHUNK_SIZE]
        rows = db.query(blombooru_media_tags.c.tag_id).filter(blombooru_media_tags.c.media_id.in_(chunk)).all()
        for r in rows:
            old_tag_ids.add(r[0])

    # 5. Delete existing media tags for requested_ids
    for i in range(0, len(requested_ids), BATCH_CHUNK_SIZE):
        chunk = requested_ids[i:i + BATCH_CHUNK_SIZE]
        db.execute(
            blombooru_media_tags.delete().where(blombooru_media_tags.c.media_id.in_(chunk))
        )

    # 6. Build new associations
    new_associations = []
    affected_tag_ids = set(old_tag_ids)

    for item in payload.items:
        item_tag_set = {}
        for raw_tag in item.tags:
            norm = raw_tag.strip().lower()
            if not norm:
                continue
            resolved_name = alias_map[norm][0].lower() if norm in alias_map else norm
            tag_obj = existing_tags_map.get(resolved_name)
            if tag_obj:
                item_tag_set[tag_obj.id] = tag_obj

        expand_implications(db, item_tag_set)

        for tid in item_tag_set.keys():
            affected_tag_ids.add(tid)
            new_associations.append({"media_id": item.id, "tag_id": tid})

    if new_associations:
        db.execute(blombooru_media_tags.insert(), new_associations)

    db.commit()

    # 7. Aggregate update tag counts
    if affected_tag_ids:
        update_tag_counts(db, list(affected_tag_ids))
        db.commit()

    try:
        invalidate_tag_cache()
    except Exception:
        pass

    return BulkTagUpdateResponse(
        status="success",
        updated_count=len(requested_ids),
        updated_media_ids=requested_ids
    )

@router.get("/{media_id}/related")
@cache_response(expire=600, key_prefix="related_media")
async def get_related_media(
    request: Request,
    media_id: int,
    limit: int = Query(12, ge=1, le=100),
    album_id: Optional[int] = Query(None),
    rating: Optional[str] = Query(default=None),
    custom_filter: Optional[List[str]] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Get related media items using category-weighted TF-IDF similarity."""
    from ..services.similarity import similarity_index

    if not isinstance(limit, int) or limit <= 0:
        limit = 12
    if not isinstance(rating, str):
        rating = None
    if not isinstance(custom_filter, (list, tuple, str, set)):
        custom_filter = None

    if similarity_index.rebuild_pending:
        await similarity_index.wait_for_build(timeout=10.0)

    if not similarity_index.is_ready:
        return {"items": [], "status": "building"}

    album_media_ids = None
    if isinstance(album_id, int):
        album_media_ids = set(get_flattened_media_ids(db, album_id))

    has_filters = bool(rating or custom_filter)
    fetch_limit = max(limit * 5, 50) if has_filters else limit

    similar_pairs = similarity_index.get_similar_media(
        media_id=media_id,
        limit=fetch_limit,
        album_media_ids=album_media_ids
    )

    if not similar_pairs:
        return {"items": [], "status": "ready"}

    similar_ids = [mid for mid, _ in similar_pairs]
    media_query = db.query(Media).options(selectinload(Media.tags)).filter(Media.id.in_(similar_ids))

    if rating:
        ratings_list = [r.strip().lower() for r in rating.split(",") if r.strip()]
        valid_ratings = [RatingEnum[r] for r in ratings_list if r in RatingEnum.__members__]
        if valid_ratings:
            media_query = media_query.filter(Media.rating.in_(valid_ratings))

    if custom_filter:
        media_query = apply_custom_filters_or(media_query, custom_filter, db)

    media_records = media_query.all()
    media_dict = {m.id: m for m in media_records}

    items = []
    for mid in similar_ids:
        if mid in media_dict:
            items.append(MediaResponse.model_validate(media_dict[mid]))
            if len(items) >= limit:
                break

    return {"items": items, "status": "ready"}

@router.get("/{media_id}/adjacent")
async def get_adjacent_media(
    media_id: int,
    mode: Optional[str] = "search",
    album_id: Optional[int] = None,
    q: Optional[str] = None,
    rating: Optional[str] = None,
    custom_filter: Optional[List[str]] = Query(default=None),
    sort: Optional[str] = None,
    order: Optional[str] = None,
    seed: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get previous and next media IDs relative to media_id within the given context."""
    try:
        if mode == "album" and album_id is not None:
            media_query = db.query(Media.id).join(
                blombooru_album_media,
                Media.id == blombooru_album_media.c.media_id
            ).filter(
                blombooru_album_media.c.album_id == album_id
            )

            if q:
                parsed = parse_search_query(q)
                if rating and 'rating' not in parsed['meta']:
                    parsed['meta']['rating'] = [{'value': rating.lower(), 'negated': False}]
                media_query = apply_search_criteria(media_query, parsed, db)
            else:
                if rating:
                    ratings_list = [r.strip().lower() for r in rating.split(",") if r.strip()]
                    valid_ratings = [RatingEnum[r] for r in ratings_list if r in RatingEnum.__members__]
                    if valid_ratings:
                        media_query = media_query.filter(Media.rating.in_(valid_ratings))

            if custom_filter:
                media_query = apply_custom_filters_or(media_query, custom_filter, db)

            if not q or ('order' not in parsed['meta'] and 'sort' not in parsed['meta']):
                sort_by = sort if sort else settings.get_default_sort()
                sort_order = order if order else settings.get_default_order()
                media_query = media_query.order_by(None)
                media_query = apply_media_sort(
                    media_query,
                    sort_by,
                    sort_order,
                    db,
                    seed,
                    column_overrides={
                        'uploaded_at': Media.id,
                        'last_modified': Media.id,
                        'name': Media.filename,
                    },
                )
        else:
            media_query = db.query(Media.id)

            parsed = parse_search_query(q or "")
            if rating and 'rating' not in parsed['meta']:
                parsed['meta']['rating'] = [{'value': rating.lower(), 'negated': False}]

            media_query = apply_search_criteria(media_query, parsed, db)
            if custom_filter:
                media_query = apply_custom_filters_or(media_query, custom_filter, db)

            if 'order' not in parsed['meta'] and 'sort' not in parsed['meta']:
                sort_by = sort if sort else settings.get_default_sort()
                sort_order = order if order else settings.get_default_order()
                media_query = media_query.order_by(None)
                media_query = apply_media_sort(media_query, sort_by, sort_order, db, seed)

        id_rows = media_query.all()
        id_list = [r[0] for r in id_rows]

        try:
            idx = id_list.index(media_id)
            prev_id = id_list[idx - 1] if idx > 0 else None
            next_id = id_list[idx + 1] if idx < len(id_list) - 1 else None
        except ValueError:
            prev_id = None
            next_id = None

        prev_hash = None
        next_hash = None
        if prev_id:
            m_prev = db.query(Media.hash).filter(Media.id == prev_id).first()
            if m_prev:
                prev_hash = m_prev.hash
        if next_id:
            m_next = db.query(Media.hash).filter(Media.id == next_id).first()
            if m_next:
                next_hash = m_next.hash

        return {
            "prev_id": prev_id,
            "prev_hash": prev_hash,
            "next_id": next_id,
            "next_hash": next_hash
        }
    except Exception as e:
        logger.error(f"Error in get_adjacent_media: {e}")
        return {"prev_id": None, "prev_hash": None, "next_id": None, "next_hash": None}

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
    
    return extract_media_metadata(file_path)

@router.post("/", response_model=MediaResponse)
async def upload_media(
    file: UploadFile = File(None),
    scanned_path: Optional[str] = Form(None),
    rating: RatingEnum = Form(RatingEnum.safe),
    tags: str = Form(""),
    album_ids: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    category_hints: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
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
    
    if 'description' in updates.model_fields_set:
        media.description = updates.description if updates.description else None
    
    affected_tag_ids = []
    if updates.tags is not None:
        old_tag_ids = [tag.id for tag in media.tags]
        media.tags = get_or_create_tags(db, updates.tags, expand=False)
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
    delete_media_cache(file_path)
    file_path.unlink(missing_ok=True)

    if media.transcoded_path:
        transcoded_file_path = settings.BASE_DIR / media.transcoded_path
        delete_media_cache(transcoded_file_path)
        transcoded_file_path.unlink(missing_ok=True)
    
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
        effective_path = (settings.BASE_DIR / media.transcoded_path) if media.transcoded_path else (settings.BASE_DIR / media.path)
        effective_mime = format_registry.get_mime_type(effective_path.name, default=media.mime_type)
        if effective_mime and effective_mime.startswith('image/'):
            background_tasks.add_task(create_stripped_media_cache, effective_path, effective_mime)
    
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
    
    if not albums:
        return {"albums": []}
    
    album_ids = [a.id for a in albums]
    
    metrics = get_bulk_album_metrics(album_ids, db)
    
    rn_col = func.row_number().over(
        partition_by=blombooru_album_media.c.album_id,
        order_by=func.random()
    ).label("rn")

    subq = db.query(
        blombooru_album_media.c.album_id,
        Media.id.label("media_id"),
        rn_col
    ).join(
        Media, Media.id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id.in_(album_ids),
        Media.thumbnail_path.isnot(None)
    ).subquery()

    thumbnail_rows = db.query(
        subq.c.album_id,
        subq.c.media_id
    ).filter(subq.c.rn <= 4).all()

    thumbnails_map: dict = {aid: [] for aid in album_ids}
    for aid, mid in thumbnail_rows:
        thumbnails_map[aid].append(f"/api/media/{mid}/thumbnail")
    
    result = []
    for album in albums:
        m = metrics.get(album.id, {"rating": "safe", "count": 0})
        result.append(AlbumListResponse(
            id=album.id,
            name=album.name,
            last_modified=album.last_modified,
            thumbnail_paths=thumbnails_map.get(album.id, []),
            rating=m["rating"],
            media_count=m["count"]
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
    upload_id: Optional[str] = Form(None),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
    current_user: User = Depends(require_admin_mode)
):
    """Receive a single chunk of an archive upload."""
    import re

    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=400, detail="Invalid chunk_index")

    if chunk_index == 0 and not upload_id:
        upload_id = str(uuid.uuid4())
    elif not upload_id or not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid or missing upload_id")

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

    return {"upload_id": upload_id, "received": chunk_index, "total": total_chunks}

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
        from ..utils.format_registry import format_registry, FormatCategory
        valid_types = set(
            format_registry.get_supported_mime_types(FormatCategory.IMAGE)
            + format_registry.get_supported_mime_types(FormatCategory.VIDEO)
        )
        file_index = 0
        for extracted_file in extract_dir.rglob('*'):
            if extracted_file.is_symlink():
                continue

            if extracted_file.is_file():
                mime_type, _ = mimetypes.guess_type(extracted_file.name)
                fmt = format_registry.get_format(extracted_file.name)
                if mime_type in valid_types or (fmt and fmt.category in (FormatCategory.IMAGE, FormatCategory.VIDEO)):
                    if not mime_type and fmt:
                        mime_type = fmt.mime_type
                    # Rename to a predictable indexed name for serving
                    original_name = extracted_file.name
                    ext = extracted_file.suffix
                    indexed_name = f"{file_index}{ext}"
                    target = extract_dir / indexed_name
                    if extracted_file != target:
                        extracted_file.rename(target)

                    file_list.append({
                        'file_id': file_index,
                        'filename': original_name,
                        'mime_type': mime_type,
                        'url': f"/api/media/archive-file/{upload_id}/{file_index}",
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
    upload_id: Optional[str] = Form(None),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
    current_user: User = Depends(require_admin_mode)
):
    """Receive a single chunk of a media upload."""
    import re

    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=400, detail="Invalid chunk_index")

    if chunk_index == 0 and not upload_id:
        upload_id = str(uuid.uuid4())
    elif not upload_id or not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid or missing upload_id")

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

    return {"upload_id": upload_id, "received": chunk_index, "total": total_chunks}

@router.post("/upload-finalize", response_model=MediaResponse)
async def finalize_chunked_upload(
    upload_id: str = Form(...),
    rating: RatingEnum = Form(RatingEnum.safe),
    tags: str = Form(""),
    album_ids: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    category_hints: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
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
                description=description,
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
