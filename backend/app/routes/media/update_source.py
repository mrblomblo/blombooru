import shutil
from pathlib import Path
from typing import Optional
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload, selectinload
from ...auth import require_admin_mode
from ...config import settings
from ...database import get_db
from ...enums import RatingEnum
from ...models import Album, Media, User
from ...schemas import MediaDetailResponse
from ...services import near_duplicates
from ...utils.album_path_resolver import ensure_album_path
from ...utils.album_utils import handle_media_rating_changed, recalculate_album_metrics, update_album_last_modified
from ...utils.cache import (
    invalidate_album_cache,
    invalidate_media_cache,
    invalidate_media_item_cache,
    invalidate_tag_cache,
)
from ...utils.logger import logger
from ...utils.media_helpers import (
    delete_media_cache,
    get_unique_filename,
    rebuild_stripped_cache_if_needed,
    sanitize_filename,
)
from ...utils.media_processor import calculate_file_hash, process_media_file
from ...utils.request_helpers import safe_error_detail
from ...utils.tag_utils import get_escalated_rating, get_newly_added_tags
from ...utils.thumbnail_generator import THUMBNAIL_EXT, generate_thumbnail
from ...utils.transcoder import (
    get_transcode_target_ext,
    get_transcoded_path_for_original,
    is_transcoding_required,
    transcode_media_if_needed,
)
from ...utils.url_fetch import UrlFetchError, safe_request
from .chunked import MEDIA_CHUNKS_DIR
from .ingestion import sync_description_enlarged
from .tags import (
    apply_media_tag_implications,
    get_or_create_tags_with_implications,
    resolve_media_tag_update,
    update_tag_counts,
)

router = APIRouter()

class StagedFileRef(BaseModel):
    """Points at a file staged in an upload session (used instead of downloading a file_url)."""
    session_id: str
    item_id: str

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
    update_custom_date: bool = False
    custom_date: Optional[str] = None
    staged_file: Optional[StagedFileRef] = None
    update_albums: bool = False
    album_ids: Optional[list[int]] = None
    album_path: Optional[str] = None

def _resolve_staged_file(ref: StagedFileRef) -> Path:
    """Locate the file of a staged upload-session item (404 if the session/item/file is gone)."""
    from ..uploads import _get_session_dir, _load_session_meta
    session_dir = _get_session_dir(ref.session_id)
    item = _load_session_meta(session_dir).get("items", {}).get(ref.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Staged item not found")
    if item.get("source_path"):
        path = Path(item["source_path"])
    else:
        path = session_dir / "raw" / item.get("staged_filename", "")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Staged file not found")
    return path

@router.patch("/{media_id}/update-from-source", response_model=MediaDetailResponse)
async def update_from_source(
    media_id: int,
    req: PostUpdateRequest,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Update an existing post's metadata and/or media file.

    Supports selective overwriting: callers set update_* flags for only the
    fields they want changed.
    """
    media = db.query(Media).options(joinedload(Media.tags), selectinload(Media.media_tag_links)).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    affected_tag_ids: list[int] = []
    newly_added_tags: list = []
    implied_by_tag_id_update: Optional[dict[int, list[list[int]]]] = None

    if req.update_tags and req.tags is not None:
        old_tag_ids = [tag.id for tag in media.tags]
        previous_tags = list(media.tags)

        if req.merge_tags:
            existing_names = {tag.name.lower() for tag in media.tags}
            merged_names = [t.name for t in media.tags] + [
                t for t in req.tags if t.strip().lower() not in existing_names
            ]
            tags_list, implied_by_tag_id_update = resolve_media_tag_update(
                db,
                media.id,
                merged_names,
                client_implied_tags=None,
                category_hints=req.category_hints,
                expand=True,
            )
            media.tags = tags_list
        else:
            tags_list, implied_by_tag_id_update = get_or_create_tags_with_implications(
                db, req.tags, category_hints=req.category_hints, expand=True
            )
            media.tags = tags_list

        new_tag_ids = [tag.id for tag in media.tags]
        affected_tag_ids = list(set(old_tag_ids + new_tag_ids))
        newly_added_tags = get_newly_added_tags(previous_tags, media.tags)

    rating_changed = False
    filename_changed = False
    file_updated = False
    if req.update_rating and req.rating:
        norm_rating = RatingEnum.normalize(req.rating)
        if norm_rating and media.rating != norm_rating:
            media.rating = norm_rating
            rating_changed = True

    # Only tags added by this request escalate, and never over a rating the
    # request explicitly asked to apply.
    if newly_added_tags and not (req.update_rating and req.rating):
        escalated = get_escalated_rating(media.rating, newly_added_tags)
        if escalated and media.rating != escalated:
            media.rating = escalated
            rating_changed = True

    if req.update_source:
        media.source = req.source or None

    if req.update_description:
        media.description = req.description or None
        sync_description_enlarged(media)

    if req.update_custom_date:
        if not req.custom_date or not str(req.custom_date).strip():
            raise HTTPException(status_code=422, detail="custom_date is required when update_custom_date is true")
        from ...utils.date_extractor import parse_explicit_custom_date
        parsed_dt = parse_explicit_custom_date(req.custom_date)
        if parsed_dt is None:
            raise HTTPException(status_code=422, detail="Invalid custom_date format")
        media.custom_date = parsed_dt

    if req.update_filename and req.filename:
        new_filename = sanitize_filename(req.filename)
        if new_filename and new_filename != media.filename:
            filename_changed = True
            old_path = settings.BASE_DIR / media.path
            new_unique = get_unique_filename(settings.ORIGINAL_DIR, new_filename)
            new_path = settings.ORIGINAL_DIR / new_unique

            if old_path.exists():
                old_path.rename(new_path)

            # Handle transcoded file rename/move if needed
            needs_transcode = is_transcoding_required(new_path)
            if needs_transcode is True:
                target_ext = get_transcode_target_ext(new_path)
                new_transc_path = get_transcoded_path_for_original(new_path, target_ext)
                if media.transcoded_path:
                    old_transc_path = settings.BASE_DIR / media.transcoded_path
                    if old_transc_path.exists():
                        delete_media_cache(media)
                        new_transc_path.parent.mkdir(parents=True, exist_ok=True)
                        old_transc_path.rename(new_transc_path)
                        media.transcoded_path = str(new_transc_path.relative_to(settings.BASE_DIR))
                    else:
                        trans_file = transcode_media_if_needed(new_path)
                        media.transcoded_path = str(trans_file.relative_to(settings.BASE_DIR)) if trans_file else None
                else:
                    trans_file = transcode_media_if_needed(new_path)
                    media.transcoded_path = str(trans_file.relative_to(settings.BASE_DIR)) if trans_file else None
            elif needs_transcode is False:
                if media.transcoded_path:
                    old_transc_path = settings.BASE_DIR / media.transcoded_path
                    if old_transc_path.exists():
                        delete_media_cache(media)
                        old_transc_path.unlink(missing_ok=True)
                    media.transcoded_path = None

            if media.thumbnail_path:
                old_thumb = settings.BASE_DIR / media.thumbnail_path
                new_thumb_name = Path(new_unique).stem + old_thumb.suffix
                new_thumb = settings.THUMBNAIL_DIR / new_thumb_name
                if old_thumb.exists():
                    old_thumb.rename(new_thumb)
                media.thumbnail_path = str(new_thumb.relative_to(settings.BASE_DIR))

            media.filename = new_unique
            media.path = str(new_path.relative_to(settings.BASE_DIR))

    if req.update_file:
        if not req.file_url and not req.staged_file:
            raise HTTPException(status_code=400, detail="file_url or staged_file is required when update_file is true")

        staged_source: Optional[Path] = _resolve_staged_file(req.staged_file) if req.staged_file else None
        dl = None
        if staged_source is None:
            import requests as _requests
            try:
                from ...services.booru import get_user_agent_for_url
                user_agent = get_user_agent_for_url(req.file_url, db=db)
                dl = safe_request(
                    "GET",
                    req.file_url,
                    timeout=60,
                    stream=True,
                    user_agent=user_agent,
                    proxies=settings.get_booru_proxies(),
                )
                dl.raise_for_status()
            except UrlFetchError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            except _requests.HTTPError as e:
                raise HTTPException(status_code=502, detail=safe_error_detail("Failed to download replacement file", e))
            except _requests.RequestException as e:
                raise HTTPException(status_code=502, detail=safe_error_detail("Failed to download replacement file", e))

        suffix = (staged_source.suffix if staged_source else Path(req.file_url.split("?")[0]).suffix) or ".bin"
        import tempfile
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                if staged_source is not None:
                    with open(staged_source, "rb") as staged_fh:
                        shutil.copyfileobj(staged_fh, tmp)
                else:
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
            delete_media_cache(media)
            old_file.unlink(missing_ok=True)

            if media.transcoded_path:
                old_transc = settings.BASE_DIR / media.transcoded_path
                old_transc.unlink(missing_ok=True)
                media.transcoded_path = None

            shutil.move(str(tmp_path), str(old_file))
            tmp_path = None

            new_meta = process_media_file(old_file, precalculated_hash=new_hash)

            # Regenerate thumbnail
            if media.thumbnail_path:
                old_thumb = settings.BASE_DIR / media.thumbnail_path
                old_thumb.unlink(missing_ok=True)

            thumb_name = Path(media.filename).stem + THUMBNAIL_EXT
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
            file_updated = True

        except HTTPException:
            raise
        except Exception as e:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            logger.exception("Error replacing media file")
            raise HTTPException(status_code=500, detail=safe_error_detail("File replacement failed", e))

    affected_album_ids: set[int] = set()
    if req.update_albums:
        wanted_album_ids = set(req.album_ids or [])
        if req.album_path:
            leaf_album, touched_ids = ensure_album_path(db, req.album_path)
            if leaf_album:
                wanted_album_ids.add(leaf_album.id)
                affected_album_ids.update(touched_ids)
        if wanted_album_ids:
            already_in = {album.id for album in media.albums}
            for album in db.query(Album).filter(Album.id.in_(wanted_album_ids)).all():
                if album.id not in already_in:
                    media.albums.append(album)
                affected_album_ids.add(album.id)

    if file_updated:
        near_duplicates.refresh_media_phash(media)

    db.flush()
    if implied_by_tag_id_update is not None:
        apply_media_tag_implications(db, media, implied_by_tag_id_update)
    db.commit()
    if file_updated:
        near_duplicates.near_duplicate_index.invalidate()

    if rating_changed:
        handle_media_rating_changed(db, media_id, media.rating.value if hasattr(media.rating, "value") else media.rating)

    if affected_tag_ids:
        update_tag_counts(db, affected_tag_ids)
        db.commit()

    if affected_album_ids:
        update_album_last_modified(list(affected_album_ids), db)
        recalculate_album_metrics(db, list(affected_album_ids))
        db.commit()
        invalidate_album_cache()

    db.refresh(media)
    invalidate_media_cache()
    invalidate_media_item_cache(media_id)
    invalidate_tag_cache()

    if file_updated or filename_changed:
        await rebuild_stripped_cache_if_needed(media, background_tasks)

    return MediaDetailResponse.model_validate(media)

@router.post("/{media_id}/update-file-finalize", response_model=MediaDetailResponse)
async def update_file_finalize(
    media_id: int,
    upload_id: str = Form(...),
    update_filename: bool = Form(False),
    update_custom_date: bool = Form(False),
    background_tasks: BackgroundTasks = None,
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

    media = db.query(Media).options(joinedload(Media.tags), selectinload(Media.media_tag_links)).filter(Media.id == media_id).first()
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
            delete_media_cache(media)
            old_file.unlink(missing_ok=True)

        if media.transcoded_path:
            old_transc = settings.BASE_DIR / media.transcoded_path
            old_transc.unlink(missing_ok=True)
            media.transcoded_path = None

        shutil.move(str(tmp_assembled), str(target_file))

        shutil.rmtree(chunk_dir, ignore_errors=True)

        new_meta = process_media_file(target_file, precalculated_hash=new_hash)

        # Regenerate thumbnail
        if media.thumbnail_path:
            old_thumb = settings.BASE_DIR / media.thumbnail_path
            old_thumb.unlink(missing_ok=True)

        thumb_name = Path(target_filename).stem + THUMBNAIL_EXT
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

        if update_custom_date:
            from ...utils.date_extractor import extract_embedded_date
            embedded_dt = extract_embedded_date(target_file)
            if embedded_dt is not None:
                media.custom_date = embedded_dt

        near_duplicates.refresh_media_phash(media)
        db.commit()
        near_duplicates.near_duplicate_index.invalidate()
        db.refresh(media)
        invalidate_media_cache()
        invalidate_media_item_cache(media_id)

        await rebuild_stripped_cache_if_needed(media, background_tasks)

        return MediaDetailResponse.model_validate(media)

    except HTTPException:
        raise
    except Exception as e:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        logger.exception("Error in update-file-finalize")
        raise HTTPException(status_code=500, detail=safe_error_detail("File update failed", e))
