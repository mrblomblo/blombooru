import asyncio
import json
import shutil
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Union

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_admin_mode
from ..config import settings
from ..database import get_db
from ..enums import FileTypeEnum, RatingEnum, TagCategoryEnum
from ..models import (Album, Media, Tag, User)
from ..schemas import (PendingAlbumEntity, PendingEntitiesResponse,
                       PendingTagEntity, PendingTagUpdate, ProposedTag,
                       UploadSessionAddUntrackedRequest,
                       UploadSessionCommitItemResult,
                       UploadSessionCommitResponse,
                       UploadSessionItemUpdate)
from ..utils.album_utils import update_album_last_modified
from ..utils.cache import (invalidate_album_cache, invalidate_media_cache,
                           invalidate_tag_cache)
from ..utils.logger import logger
from ..utils.media_helpers import extract_media_metadata, get_unique_filename
from ..utils.media_processor import calculate_file_hash, process_media_file
from ..utils.request_helpers import safe_error_detail
from ..utils.thumbnail_generator import generate_thumbnail
from ..utils.transcoder import transcode_media_if_needed
from .media import preview_or_create_tags, update_tag_counts

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOAD_SESSIONS_DIR = settings.CACHE_DIR / "upload-sessions"
UPLOAD_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

_session_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

def _get_session_lock(session_id: str) -> asyncio.Lock:
    safe_id = Path(session_id).name
    return _session_locks[safe_id]

def cleanup_upload_sessions(max_age_seconds: int = 3600):
    """Clean up upload session directories older than max_age_seconds."""
    if not UPLOAD_SESSIONS_DIR.exists():
        return
    cutoff = time.time() - max_age_seconds
    for session_dir in UPLOAD_SESSIONS_DIR.iterdir():
        if session_dir.is_dir():
            try:
                meta_path = session_dir / "meta.json"
                mtime = meta_path.stat().st_mtime if meta_path.exists() else session_dir.stat().st_mtime
                if mtime < cutoff:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    _session_locks.pop(session_dir.name, None)
                    logger.debug(f"Cleaned up stale upload session: {session_dir.name}")
            except Exception as e:
                logger.error(f"Error cleaning up upload session {session_dir}: {e}")

def _get_session_dir(session_id: str) -> Path:
    safe_id = Path(session_id).name
    session_dir = UPLOAD_SESSIONS_DIR / safe_id
    if not session_dir.exists() or not session_dir.is_dir():
        raise HTTPException(status_code=404, detail="Upload session not found or expired")
    return session_dir

def _load_session_meta(session_dir: Path) -> dict:
    meta_path = session_dir / "meta.json"
    if not meta_path.exists():
        return {"session_id": session_dir.name, "created_at": time.time(), "items": {}}
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading session metadata {meta_path}: {e}")
        return {"session_id": session_dir.name, "created_at": time.time(), "items": {}}

def _save_session_meta(session_dir: Path, meta: dict) -> None:
    meta_path = session_dir / "meta.json"
    meta["updated_at"] = time.time()
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving session metadata {meta_path}: {e}")

def _get_session_pending_tags_map(items: dict) -> Dict[str, dict]:
    """Extract a mapping of tag_name -> {category, user_assigned} for all pending/new tags in the session.
    User-assigned categories take precedence."""
    tag_map: Dict[str, dict] = {}
    for item in items.values():
        for t in item.get("tags", []):
            if t.get("is_new", False):
                name = t.get("name", "").strip().lower()
                if not name:
                    continue
                cat = t.get("category", "general")
                user_assigned = t.get("user_assigned", False)
                if name not in tag_map:
                    tag_map[name] = {"category": cat, "user_assigned": user_assigned}
                else:
                    if user_assigned:
                        tag_map[name]["category"] = cat
                        tag_map[name]["user_assigned"] = True
    return tag_map

class BulkUpdateRequest(BaseModel):
    item_ids: List[str]
    rating: Optional[RatingEnum] = None
    source: Optional[str] = None
    description: Optional[str] = None
    album_ids: Optional[List[int]] = None
    add_album_ids: Optional[List[int]] = None
    remove_album_ids: Optional[List[int]] = None
    suggested_album_path: Optional[str] = None
    add_tags: Optional[List[Union[str, ProposedTag]]] = None
    remove_tag_names: Optional[List[str]] = None

@router.post("/sessions")
async def create_upload_session(
    current_user: User = Depends(require_admin_mode),
):
    """Create a new staging session for confirmation-first upload review."""
    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "raw").mkdir(parents=True, exist_ok=True)
    (session_dir / "thumbs").mkdir(parents=True, exist_ok=True)

    meta = {
        "session_id": session_id,
        "created_at": time.time(),
        "updated_at": time.time(),
        "items": {},
    }
    _save_session_meta(session_dir, meta)

    return {"session_id": session_id}

@router.get("/sessions/{session_id}")
async def get_upload_session(
    session_id: str,
    current_user: User = Depends(require_admin_mode),
):
    """Retrieve full upload session state including all queued items."""
    session_dir = _get_session_dir(session_id)
    meta = _load_session_meta(session_dir)
    items_list = list(meta.get("items", {}).values())
    return {
        "session_id": session_id,
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "items": items_list,
    }

@router.delete("/sessions/{session_id}")
async def cancel_upload_session(
    session_id: str,
    current_user: User = Depends(require_admin_mode),
):
    """Cancel and delete an upload session and all staged files."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        shutil.rmtree(session_dir, ignore_errors=True)
        _session_locks.pop(Path(session_id).name, None)
        return {"status": "deleted", "session_id": session_id}

def _process_and_stage_item(
    session_dir: Path,
    meta: dict,
    item_id: str,
    file_path: Path,
    clean_filename: str,
    staged_filename: Optional[str],
    is_untracked: bool,
    relative_path: Optional[str],
    base_rating: Optional[str],
    base_source: Optional[str],
    base_tags: Optional[str],
    base_album_ids: Optional[str],
    category_hints: Optional[str],
    user_assigned_tags: Optional[str],
    base_description: Optional[str],
    db: Session,
) -> dict:
    thumbs_dir = session_dir / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    file_size = file_path.stat().st_size
    file_hash = calculate_file_hash(file_path)

    # Check for exact duplicate in DB
    existing = db.query(Media).filter(Media.hash == file_hash).first()
    if existing:
        if not is_untracked and staged_filename:
            file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail=f"admin.media_management.booru_import.error_duplicate:::{existing.filename}"
        )

    # Check if duplicate within this session
    for it in meta.get("items", {}).values():
        if it.get("hash") == file_hash and it.get("item_id") != item_id:
            if not is_untracked and staged_filename:
                file_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=409,
                detail=f"admin.media_management.booru_import.error_duplicate_session:::{it.get('filename')}"
            )

    # Analyze media dimensions and type
    try:
        media_info = process_media_file(file_path, precalculated_hash=file_hash, transcode=False)
        width = media_info.get("width")
        height = media_info.get("height")
        file_type = media_info.get("file_type")
        mime_type = media_info.get("mime_type")
        duration = media_info.get("duration")
    except Exception as e:
        logger.warning(f"Failed to process media file metadata for {clean_filename}: {e}")
        width = None
        height = None
        file_type = FileTypeEnum.image
        mime_type = None
        duration = None

    # Generate preview thumbnail in session thumbs dir
    thumb_path = thumbs_dir / f"{item_id}.jpg"
    try:
        generate_thumbnail(file_path, thumb_path, file_type)
    except Exception as e:
        logger.warning(f"Failed to generate preview thumbnail for {clean_filename}: {e}")

    # Sanitize parameter defaults if invoked directly in tests
    relative_path_str = relative_path if isinstance(relative_path, str) else None
    base_rating_str = base_rating if isinstance(base_rating, str) else None
    base_source_str = base_source if isinstance(base_source, str) else None
    base_tags_str = base_tags if isinstance(base_tags, str) else None
    base_album_ids_str = base_album_ids if isinstance(base_album_ids, str) else None
    category_hints_str = category_hints if isinstance(category_hints, str) else None
    base_description_str = base_description if isinstance(base_description, str) else None

    # Parse initial candidate tags
    candidate_tag_names: List[str] = []
    if base_tags_str:
        candidate_tag_names.extend([t.strip() for t in base_tags_str.split() if t.strip()])

    # Apply automatic tags based on media type if configured
    media_type_tags = settings.MEDIA_TYPE_TAGS
    if isinstance(media_type_tags, dict):
        ft_key = file_type.value if hasattr(file_type, "value") else str(file_type)
        type_tags = media_type_tags.get(ft_key, [])
        if isinstance(type_tags, list):
            for tag in type_tags:
                if tag and isinstance(tag, str) and tag.strip():
                    candidate_tag_names.append(tag.strip())

    # Apply automatic tags from AI metadata if configured
    if settings.AUTO_APPLY_AI_TAGS:
        try:
            extracted_meta = extract_media_metadata(file_path)
            ai_meta = extracted_meta.get("ai") if isinstance(extracted_meta, dict) else None
            if isinstance(ai_meta, dict):
                prompt_tags = ai_meta.get("prompt_tags")
                if isinstance(prompt_tags, list):
                    for tag in prompt_tags:
                        if tag and isinstance(tag, str) and tag.strip():
                            candidate_tag_names.append(tag.strip())
        except Exception as e:
            logger.warning(f"Failed to extract AI metadata tags for {clean_filename}: {e}")

    parsed_hints: Optional[dict] = None
    if category_hints_str:
        try:
            parsed_hints = json.loads(category_hints_str)
        except Exception:
            pass
            
    user_assigned_tags_str = user_assigned_tags if isinstance(user_assigned_tags, str) else None
    user_assigned_list = []
    if user_assigned_tags_str:
        try:
            user_assigned_list = json.loads(user_assigned_tags_str)
        except Exception:
            pass
    user_assigned_lower = {str(x).lower() for x in user_assigned_list}

    # Resolve candidate tags against database in dry_run mode
    proposed_tags = preview_or_create_tags(
        db,
        candidate_tag_names,
        category_hints=parsed_hints,
        expand=True,
        dry_run=True,
    )

    # Resolve initial rating
    rating = RatingEnum.safe
    if base_rating_str and base_rating_str in RatingEnum._value2member_map_:
        rating = RatingEnum(base_rating_str)

    # Resolve initial albums
    album_ids: List[int] = []
    if base_album_ids_str:
        for aid_str in base_album_ids_str.split(","):
            aid_str = aid_str.strip()
            if aid_str.isdigit():
                album_ids.append(int(aid_str))

    session_pending_map = _get_session_pending_tags_map(meta.get("items", {}))

    tags_list = []
    for t in proposed_tags:
        td = t.model_dump() if hasattr(t, "model_dump") else dict(t)
        if parsed_hints is None:
            td["user_assigned"] = True
        else:
            td["user_assigned"] = (t.name.lower() in user_assigned_lower)

        # Re-assign conflicting new tag categories to the category already used in the upload queue
        t_name = td.get("name", "").strip().lower()
        if td.get("is_new", False) and t_name in session_pending_map:
            session_info = session_pending_map[t_name]
            td["category"] = session_info["category"]
            if session_info.get("user_assigned", False):
                td["user_assigned"] = True

        tags_list.append(td)

    # Compute default relative path for untracked files
    if is_untracked and not relative_path_str:
        try:
            relative_path_str = str(file_path.resolve().relative_to(settings.ORIGINAL_DIR.resolve()))
        except Exception:
            relative_path_str = clean_filename

    item_data = {
        "item_id": item_id,
        "filename": clean_filename,
        "source_path": str(file_path) if is_untracked else None,
        "is_untracked": is_untracked,
        "staged_filename": staged_filename,
        "relative_path": relative_path_str or clean_filename,
        "file_size": file_size,
        "width": width,
        "height": height,
        "duration": duration,
        "file_type": file_type.value if hasattr(file_type, "value") else file_type,
        "mime_type": mime_type,
        "hash": file_hash,
        "rating": rating.value,
        "source": base_source_str or "",
        "description": base_description_str or "",
        "tags": tags_list,
        "album_ids": album_ids,
        "suggested_album_path": None,
    }

    meta.setdefault("items", {})[item_id] = item_data
    _save_session_meta(session_dir, meta)

    return item_data

@router.post("/sessions/{session_id}/files")
async def upload_files_to_session(
    session_id: str,
    file: UploadFile = File(...),
    relative_path: Optional[str] = Form(None),
    base_rating: Optional[str] = Form(None),
    base_source: Optional[str] = Form(None),
    base_tags: Optional[str] = Form(None),
    base_album_ids: Optional[str] = Form(None),
    category_hints: Optional[str] = Form(None),
    user_assigned_tags: Optional[str] = Form(None),
    base_description: Optional[str] = Form(None),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Upload and stage a single file in the session, hash it, and perform initial analysis."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        raw_dir = session_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        meta = _load_session_meta(session_dir)

        item_id = str(uuid.uuid4())[:12]
        clean_filename = Path(file.filename).name
        staged_filename = f"{item_id}_{clean_filename}"
        staged_path = raw_dir / staged_filename

        await file.seek(0)
        with open(staged_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)

        return _process_and_stage_item(
            session_dir=session_dir,
            meta=meta,
            item_id=item_id,
            file_path=staged_path,
            clean_filename=clean_filename,
            staged_filename=staged_filename,
            is_untracked=False,
            relative_path=relative_path,
            base_rating=base_rating,
            base_source=base_source,
            base_tags=base_tags,
            base_album_ids=base_album_ids,
            category_hints=category_hints,
            user_assigned_tags=user_assigned_tags,
            base_description=base_description,
            db=db,
        )

@router.post("/sessions/{session_id}/untracked-files")
async def add_untracked_file_to_session(
    session_id: str,
    request: UploadSessionAddUntrackedRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Stage an existing untracked file from disk into the upload session without re-uploading bytes."""
    file_path = Path(request.file_path)
    if not file_path.is_absolute():
        raise HTTPException(status_code=400, detail="Invalid file path")

    try:
        resolved_path = file_path.resolve()
        if not resolved_path.is_relative_to(settings.ORIGINAL_DIR.resolve()):
            raise ValueError()
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=403, detail="Access denied")

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        item_id = str(uuid.uuid4())[:12]

        return _process_and_stage_item(
            session_dir=session_dir,
            meta=meta,
            item_id=item_id,
            file_path=resolved_path,
            clean_filename=resolved_path.name,
            staged_filename=None,
            is_untracked=True,
            relative_path=request.relative_path,
            base_rating=request.base_rating,
            base_source=request.base_source,
            base_tags=request.base_tags,
            base_album_ids=request.base_album_ids,
            category_hints=request.category_hints,
            user_assigned_tags=request.user_assigned_tags,
            base_description=request.base_description,
            db=db,
        )

@router.get("/sessions/{session_id}/items/{item_id}/thumbnail")
async def get_staged_item_thumbnail(
    session_id: str,
    item_id: str,
):
    """Serve the temporary preview thumbnail of a staged item."""
    session_dir = _get_session_dir(session_id)
    thumb_path = session_dir / "thumbs" / f"{item_id}.jpg"
    if thumb_path.exists():
        return FileResponse(str(thumb_path), media_type="image/jpeg")

    # Fallback to source or raw file if thumbnail wasn't generated
    meta = _load_session_meta(session_dir)
    item = meta.get("items", {}).get(item_id)
    if item:
        if item.get("source_path"):
            src_path = Path(item["source_path"])
            if src_path.exists():
                return FileResponse(str(src_path))
        staged_path = session_dir / "raw" / item.get("staged_filename", "")
        if staged_path.exists():
            return FileResponse(str(staged_path))

    raise HTTPException(status_code=404, detail="Thumbnail not found")

@router.get("/sessions/{session_id}/items/{item_id}/file")
async def get_staged_item_file(
    session_id: str,
    item_id: str,
):
    """Serve the raw staged media file."""
    session_dir = _get_session_dir(session_id)
    meta = _load_session_meta(session_dir)
    item = meta.get("items", {}).get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.get("source_path"):
        src_path = Path(item["source_path"])
        if src_path.exists():
            return FileResponse(str(src_path), media_type=item.get("mime_type") or "application/octet-stream")

    staged_path = session_dir / "raw" / item.get("staged_filename", "")
    if not staged_path.exists():
        raise HTTPException(status_code=404, detail="Staged file not found")

    return FileResponse(str(staged_path), media_type=item.get("mime_type") or "application/octet-stream")

@router.post("/sessions/{session_id}/items/{item_id}/analyze")
async def analyze_staged_item(
    session_id: str,
    item_id: str,
    category_hints: Optional[str] = None,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Re-analyze staged item and refresh tag proposals."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        item = meta.get("items", {}).get(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        if item.get("source_path"):
            media_path = Path(item["source_path"])
        else:
            media_path = session_dir / "raw" / item.get("staged_filename", "")
        if not media_path.exists():
            raise HTTPException(status_code=404, detail="Media file not found")

        file_hash = item.get("hash") or calculate_file_hash(media_path)
        media_info = process_media_file(media_path, precalculated_hash=file_hash)
        item["width"] = media_info.get("width")
        item["height"] = media_info.get("height")
        item["file_type"] = media_info.get("file_type")
        item["mime_type"] = media_info.get("mime_type")
        item["duration"] = media_info.get("duration")

        thumb_path = session_dir / "thumbs" / f"{item_id}.jpg"
        generate_thumbnail(media_path, thumb_path, item["file_type"])

        # Re-evaluate current tags with DB
        current_tag_names = [t["name"] for t in item.get("tags", []) if t.get("name")]
        parsed_hints = None
        if category_hints:
            try:
                parsed_hints = json.loads(category_hints)
            except Exception:
                pass

        proposed_tags = preview_or_create_tags(
            db,
            current_tag_names,
            category_hints=parsed_hints,
            expand=True,
            dry_run=True,
        )
        item["tags"] = [t.model_dump() if hasattr(t, "model_dump") else dict(t) for t in proposed_tags]

        meta["items"][item_id] = item
        _save_session_meta(session_dir, meta)

        return item

@router.patch("/sessions/{session_id}/items/{item_id}")
async def update_staged_item(
    session_id: str,
    item_id: str,
    update: UploadSessionItemUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Update staged item properties (tags, rating, source, description, albums)."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        item = meta.get("items", {}).get(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        if update.rating is not None:
            item["rating"] = update.rating.value
        if update.source is not None:
            item["source"] = update.source
        if update.description is not None:
            item["description"] = update.description
        if update.album_ids is not None:
            item["album_ids"] = update.album_ids
        if update.suggested_album_path is not None:
            item["suggested_album_path"] = update.suggested_album_path

    if update.tags is not None:
        other_items = {k: v for k, v in meta.get("items", {}).items() if k != item_id}
        session_pending_map = _get_session_pending_tags_map(other_items)

        # Build category hints from user assigned tag categories
        hints = {t.name.lower(): t.category.value for t in update.tags}
        names = [t.name for t in update.tags]
        proposed = preview_or_create_tags(
            db,
            names,
            category_hints=hints,
            expand=True,
            dry_run=True,
        )
        # Preserve user_assigned flag if explicitly passed
        user_assigned_set = {t.name.lower() for t in update.tags if getattr(t, "user_assigned", False)}
        result_tags = []
        for pt in proposed:
            dump = pt.model_dump() if hasattr(pt, "model_dump") else dict(pt)
            t_name = dump["name"].lower()
            if t_name in user_assigned_set:
                dump["user_assigned"] = True
                if t_name in hints:
                    dump["category"] = hints[t_name]
            elif dump.get("is_new", False) and t_name in session_pending_map:
                dump["category"] = session_pending_map[t_name]["category"]
                if session_pending_map[t_name].get("user_assigned", False):
                    dump["user_assigned"] = True
            result_tags.append(dump)
        item["tags"] = result_tags

    meta["items"][item_id] = item
    _save_session_meta(session_dir, meta)

    return item

@router.post("/sessions/{session_id}/items/bulk-update")
async def bulk_update_staged_items(
    session_id: str,
    req: BulkUpdateRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Apply updates to multiple staged items at once."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        items = meta.get("items", {})

        updated_items = []
        target_ids = set(req.item_ids)

        for item_id, item in items.items():
            if item_id not in target_ids:
                continue

            if req.rating is not None:
                item["rating"] = req.rating.value
            if req.source is not None:
                item["source"] = req.source
            if req.description is not None:
                item["description"] = req.description
            if req.album_ids is not None:
                item["album_ids"] = req.album_ids
            if req.add_album_ids is not None:
                cur_aids = set(item.get("album_ids", []))
                cur_aids.update(req.add_album_ids)
                item["album_ids"] = list(cur_aids)
            if req.remove_album_ids is not None:
                cur_aids = set(item.get("album_ids", []))
                cur_aids.difference_update(req.remove_album_ids)
                item["album_ids"] = list(cur_aids)
            if req.suggested_album_path is not None:
                item["suggested_album_path"] = req.suggested_album_path

            # Tags update
            current_tags_dict = {t["name"].lower(): t for t in item.get("tags", []) if t.get("name")}

            if req.remove_tag_names:
                remove_set = {n.strip().lower() for n in req.remove_tag_names}
                current_tags_dict = {k: v for k, v in current_tags_dict.items() if k not in remove_set}

            user_assigned_map: Dict[str, str] = {}
            if req.add_tags:
                for t in req.add_tags:
                    if isinstance(t, str):
                        t_name = t.strip().lower()
                        if t_name and t_name not in current_tags_dict:
                            current_tags_dict[t_name] = {"name": t_name, "category": "general", "is_new": True, "user_assigned": False}
                    else:
                        t_name = t.name.strip().lower()
                        if t_name:
                            is_user_assigned = getattr(t, "user_assigned", False) or t.category != TagCategoryEnum.general
                            current_tags_dict[t_name] = {
                                "name": t_name,
                                "category": t.category.value,
                                "is_new": t.is_new,
                                "user_assigned": is_user_assigned,
                            }
                            if is_user_assigned:
                                user_assigned_map[t_name] = t.category.value

            # Re-evaluate with preview_or_create_tags
            names = list(current_tags_dict.keys())
            hints = {k: v["category"] for k, v in current_tags_dict.items() if v.get("category")}
            hints.update(user_assigned_map)

            other_items = {k: v for k, v in items.items() if k != item_id}
            session_pending_map = _get_session_pending_tags_map(other_items)

            proposed = preview_or_create_tags(
                db,
                names,
                category_hints=hints,
                expand=True,
                dry_run=True,
            )
            resolved_tags = []
            for pt in proposed:
                pt_dict = pt.model_dump() if hasattr(pt, "model_dump") else dict(pt)
                t_name = pt.name.lower()
                # Preserve user_assigned flag if set
                orig = current_tags_dict.get(t_name)
                if orig and orig.get("user_assigned", False):
                    pt_dict["user_assigned"] = True
                elif pt_dict.get("is_new", False) and t_name in session_pending_map:
                    pt_dict["category"] = session_pending_map[t_name]["category"]
                    if session_pending_map[t_name].get("user_assigned", False):
                        pt_dict["user_assigned"] = True
                resolved_tags.append(pt_dict)

            item["tags"] = resolved_tags

            items[item_id] = item
            updated_items.append(item)

        _save_session_meta(session_dir, meta)
        return {"updated_count": len(updated_items), "items": updated_items}

@router.delete("/sessions/{session_id}/items/{item_id}")
async def delete_staged_item(
    session_id: str,
    item_id: str,
    current_user: User = Depends(require_admin_mode),
):
    """Delete a single staged item from the session."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        items = meta.get("items", {})

        if item_id not in items:
            raise HTTPException(status_code=404, detail="Item not found in upload session")

        staged_filename = items[item_id].get("staged_filename")
        if staged_filename:
            (session_dir / "raw" / staged_filename).unlink(missing_ok=True)
        (session_dir / "thumbs" / f"{item_id}.jpg").unlink(missing_ok=True)

        del items[item_id]
        if len(items) == 0:
            shutil.rmtree(session_dir, ignore_errors=True)
            _session_locks.pop(Path(session_id).name, None)
            return {"status": "session_deleted", "item_id": item_id, "session_empty": True}

        _save_session_meta(session_dir, meta)
        return {"status": "deleted", "item_id": item_id, "session_empty": False}

@router.get("/sessions/{session_id}/pending")
async def get_pending_entities(
    session_id: str,
    current_user: User = Depends(require_admin_mode),
):
    """Aggregate and deduplicate all pending new tags and albums across the session."""
    session_dir = _get_session_dir(session_id)
    meta = _load_session_meta(session_dir)
    items = meta.get("items", {})

    pending_tags_map: Dict[str, dict] = {}
    pending_albums_map: Dict[str, List[str]] = {}

    for item_id, item in items.items():
        if item.get("is_duplicate", False):
            continue

        for t in item.get("tags", []):
            # Include all new tags, even if they have been assigned a category manually
            if t.get("is_new", False):
                name = t.get("name", "").strip().lower()
                if not name:
                    continue
                if name not in pending_tags_map:
                    pending_tags_map[name] = {
                        "name": name,
                        "category": t.get("category", "general"),
                        "used_by": [],
                        "merge_into": t.get("merge_into"),
                        "user_assigned": t.get("user_assigned", False),
                    }
                else:
                    if t.get("user_assigned", False):
                        pending_tags_map[name]["user_assigned"] = True
                if item_id not in pending_tags_map[name]["used_by"]:
                    pending_tags_map[name]["used_by"].append(item_id)

        suggested_path = item.get("suggested_album_path")
        if suggested_path:
            norm_path = suggested_path.strip().strip("/")
            if norm_path:
                if norm_path not in pending_albums_map:
                    pending_albums_map[norm_path] = []
                if item_id not in pending_albums_map[norm_path]:
                    pending_albums_map[norm_path].append(item_id)

    pending_tags = [PendingTagEntity(**v) for v in pending_tags_map.values()]
    pending_albums = [PendingAlbumEntity(path=k, used_by=v) for k, v in pending_albums_map.items()]

    return PendingEntitiesResponse(
        pending_tags=pending_tags,
        pending_albums=pending_albums,
    )

@router.patch("/sessions/{session_id}/pending/tags/{tag_name}")
async def update_pending_tag(
    session_id: str,
    tag_name: str,
    update: PendingTagUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Globally update a pending tag (rename, change category, merge into existing, or remove) across all referencing items."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        items = meta.get("items", {})

        target_name = tag_name.strip().lower()
        affected_count = 0

        for item_id, item in items.items():
            tags = item.get("tags", [])
            new_tags = []
            modified = False

            for t in tags:
                current_name = t.get("name", "").strip().lower()
                if current_name == target_name:
                    modified = True
                    if update.remove:
                        continue  # Remove tag from this item

                    if update.merge_into:
                        merge_target = update.merge_into.strip().lower()
                        # Check if merge_target exists in DB
                        existing_db_tag = db.query(Tag).filter(Tag.name == merge_target).first()
                        t["name"] = merge_target
                        t["is_new"] = existing_db_tag is None
                        t["category"] = existing_db_tag.category.value if existing_db_tag else t.get("category", "general")
                        t["user_assigned"] = True
                        new_tags.append(t)
                    else:
                        if update.new_name:
                            t["name"] = update.new_name.strip().lower()
                        if update.category:
                            t["category"] = update.category.value
                        t["user_assigned"] = True
                        new_tags.append(t)
                else:
                    new_tags.append(t)

            if modified:
                # Deduplicate item's tags by name
                seen = set()
                deduped = []
                for t in new_tags:
                    n = t["name"].lower()
                    if n not in seen:
                        seen.add(n)
                        deduped.append(t)
                item["tags"] = deduped
                items[item_id] = item
                affected_count += 1

        _save_session_meta(session_dir, meta)
        return {"status": "updated", "affected_items": affected_count}

@router.post("/sessions/{session_id}/commit", response_model=UploadSessionCommitResponse)
async def commit_upload_session(
    session_id: str,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Commit the staged session in a single database transaction."""
    async with _get_session_lock(session_id):
        session_dir = _get_session_dir(session_id)
        meta = _load_session_meta(session_dir)
        items = meta.get("items", {})

        if not items:
            raise HTTPException(status_code=400, detail="No items to commit in this session")

        results: List[UploadSessionCommitItemResult] = []
        total_created = 0
        total_duplicates = 0
        total_failed = 0

        all_tag_ids_to_update: set[int] = set()
        all_affected_album_ids: set[int] = set()

        try:
            # Pre-scan for duplicate items (both pre-marked and hash collision against DB)
            duplicate_item_ids: set[str] = set()
            for i_id, item in items.items():
                if item.get("is_duplicate"):
                    duplicate_item_ids.add(i_id)
                    continue
                if item.get("source_path"):
                    file_to_check = Path(item["source_path"])
                else:
                    file_to_check = session_dir / "raw" / item.get("staged_filename", "")
                f_hash = item.get("hash") or (calculate_file_hash(file_to_check) if file_to_check.exists() else None)
                if f_hash and db.query(Media.id).filter(Media.hash == f_hash).first():
                    duplicate_item_ids.add(i_id)

            # Step 1: Gather and bulk create all confirmed new tags (skipping duplicate items)
            pending_tags_to_create: Dict[str, str] = {}
            for i_id, item in items.items():
                if i_id in duplicate_item_ids:
                    continue
                for t in item.get("tags", []):
                    t_name = t.get("name", "").strip().lower()
                    if not t_name:
                        continue
                    if t.get("is_new", False):
                        cat = t.get("category", "general")
                        pending_tags_to_create[t_name] = cat

            if pending_tags_to_create:
                existing_db_tags = {
                    t.name: t for t in db.query(Tag).filter(Tag.name.in_(list(pending_tags_to_create.keys()))).all()
                }
                for t_name, t_cat in pending_tags_to_create.items():
                    if t_name not in existing_db_tags:
                        new_tag = Tag(name=t_name, post_count=0, category=t_cat)
                        db.add(new_tag)
                db.flush()

            # Step 2: Resolve and create any suggested albums (skipping duplicate items)
            album_path_cache: Dict[str, Album] = {}
            for i_id, item in items.items():
                if i_id in duplicate_item_ids:
                    continue
                suggested_path = item.get("suggested_album_path")
                if suggested_path:
                    segments = [s.strip() for s in suggested_path.strip("/").split("/") if s.strip()]
                    if segments:
                        current_parent_album = None
                        path_key = ""
                        for seg in segments:
                            path_key = f"{path_key}/{seg}" if path_key else seg
                            if path_key in album_path_cache:
                                current_parent_album = album_path_cache[path_key]
                            else:
                                alb = db.query(Album).filter(Album.name == seg).first()
                                if not alb:
                                    alb = Album(name=seg)
                                    db.add(alb)
                                    db.flush()
                                if current_parent_album and alb not in current_parent_album.children:
                                    current_parent_album.children.append(alb)
                                    db.flush()
                                album_path_cache[path_key] = alb
                                current_parent_album = alb

                        # Assign leaf album to item's album_ids
                        leaf_album = album_path_cache[path_key]
                        current_aids = set(item.get("album_ids", []))
                        current_aids.add(leaf_album.id)
                        item["album_ids"] = list(current_aids)

            # Step 3: Commit each media item
            for item_id, item in items.items():
                clean_filename = item.get("filename", "media")
                is_untracked = bool(item.get("is_untracked") or item.get("source_path"))

                if is_untracked:
                    source_path_str = item.get("source_path")
                    source_path = Path(source_path_str) if source_path_str else None
                    if not source_path or not source_path.exists():
                        total_failed += 1
                        results.append(UploadSessionCommitItemResult(
                            item_id=item_id,
                            filename=clean_filename,
                            status="failed",
                            error="Source file not found",
                        ))
                        continue
                    file_to_process = source_path
                else:
                    staged_path = session_dir / "raw" / item.get("staged_filename", "")
                    if not staged_path.exists():
                        total_failed += 1
                        results.append(UploadSessionCommitItemResult(
                            item_id=item_id,
                            filename=clean_filename,
                            status="failed",
                            error="Staged file not found",
                        ))
                        continue
                    file_to_process = staged_path

                file_hash = item.get("hash") or calculate_file_hash(file_to_process)

                # Check duplicate in DB or marked duplicate
                if item_id in duplicate_item_ids:
                    existing = db.query(Media).filter(Media.hash == file_hash).first()
                    total_duplicates += 1
                    dup_filename = existing.filename if existing else (item.get("duplicate_of") or clean_filename)
                    results.append(UploadSessionCommitItemResult(
                        item_id=item_id,
                        filename=clean_filename,
                        media_id=existing.id if existing else None,
                        status="duplicate",
                        error=f"Duplicate of {dup_filename}",
                    ))
                    continue

                if is_untracked:
                    dest_path = file_to_process
                    unique_filename = dest_path.name
                else:
                    # Move staged file to original destination
                    unique_filename = get_unique_filename(settings.ORIGINAL_DIR, clean_filename)
                    dest_path = settings.ORIGINAL_DIR / unique_filename
                    shutil.move(str(staged_path), str(dest_path))

                # Transcode if container/codec requires it
                transcoded_file_path = transcode_media_if_needed(dest_path)
                rel_transcoded = str(transcoded_file_path.relative_to(settings.BASE_DIR)) if transcoded_file_path else None

                # Generate final thumbnail
                thumb_filename = Path(unique_filename).stem + ".jpg"
                thumb_dest_path = settings.THUMBNAIL_DIR / thumb_filename
                file_type_str = item.get("file_type", "image")
                thumb_source = transcoded_file_path if transcoded_file_path else dest_path
                thumb_gen = generate_thumbnail(thumb_source, thumb_dest_path, file_type_str)

                rel_path = dest_path.relative_to(settings.BASE_DIR)
                rel_thumb = thumb_dest_path.relative_to(settings.BASE_DIR) if thumb_gen else None

                # Create Media DB record
                media = Media(
                    filename=unique_filename,
                    path=str(rel_path),
                    transcoded_path=rel_transcoded,
                    thumbnail_path=str(rel_thumb) if rel_thumb else None,
                    hash=file_hash,
                    file_type=FileTypeEnum(file_type_str) if file_type_str in FileTypeEnum._value2member_map_ else FileTypeEnum.image,
                    mime_type=item.get("mime_type"),
                    file_size=item.get("file_size", 0),
                    width=item.get("width"),
                    height=item.get("height"),
                    duration=item.get("duration"),
                    rating=RatingEnum(item.get("rating", "safe")),
                    source=item.get("source") or None,
                    description=item.get("description") or None,
                )

                # Link tags
                item_tag_names = [t.get("name", "").strip().lower() for t in item.get("tags", []) if t.get("name")]
                if item_tag_names:
                    media.tags = preview_or_create_tags(db, item_tag_names, expand=True, dry_run=False)
                    for t in media.tags:
                        all_tag_ids_to_update.add(t.id)

                # Link albums
                a_ids = item.get("album_ids", [])
                if a_ids:
                    albums = db.query(Album).filter(Album.id.in_(a_ids)).all()
                    media.albums = albums
                    for alb in albums:
                        all_affected_album_ids.add(alb.id)

                db.add(media)
                db.flush()

                total_created += 1
                results.append(UploadSessionCommitItemResult(
                    item_id=item_id,
                    filename=clean_filename,
                    media_id=media.id,
                    status="created",
                ))

            # Commit transaction
            db.commit()

            # Update tag counts and album modified times
            if all_tag_ids_to_update:
                update_tag_counts(db, list(all_tag_ids_to_update))
                db.commit()

            if all_affected_album_ids:
                for aid in all_affected_album_ids:
                    update_album_last_modified(aid, db)
                db.commit()
                invalidate_album_cache()

            invalidate_media_cache()
            invalidate_tag_cache()

            # Clean up session directory
            shutil.rmtree(session_dir, ignore_errors=True)
            _session_locks.pop(Path(session_id).name, None)

            return UploadSessionCommitResponse(
                results=results,
                total_created=total_created,
                total_duplicates=total_duplicates,
                total_failed=total_failed,
            )

        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to commit upload session {session_id}")
            raise HTTPException(status_code=500, detail=safe_error_detail("Failed to commit upload session", e))
