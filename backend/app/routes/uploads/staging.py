import json
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ...auth import require_admin_mode
from ...config import settings
from ...database import get_db
from ...enums import FileTypeEnum, RatingEnum
from ...models import Media, User
from ...schemas import UploadSessionAddUntrackedRequest
from ...services import near_duplicates
from ...services.metadata_parsers import get_parser_for_file
from ...utils.album_path_resolver import derive_item_suggested_album_path, resolve_album_path
from ...utils.logger import logger
from ...utils.media_helpers import extract_media_metadata
from ...utils.media_processor import calculate_file_hash, process_media_file
from ...utils.tag_utils import get_escalated_rating
from ...utils.thumbnail_generator import THUMBNAIL_EXT, generate_thumbnail, thumbnail_mime_type
from ..media import preview_or_create_tags
from .session_store import (
    _get_session_dir,
    _get_session_lock,
    _get_session_pending_tags_map,
    _load_session_meta,
    _save_session_meta,
)

router = APIRouter()

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
    folder_mapping_mode: Optional[str] = "use_root",
    client_date: Optional[str] = None,
    booru_date: Optional[str] = None,
    custom_date: Optional[str] = None,
) -> dict:
    thumbs_dir = session_dir / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    file_size = file_path.stat().st_size
    file_hash = calculate_file_hash(file_path)

    # Check for exact duplicate in DB
    existing = db.query(Media).filter(Media.hash == file_hash).first()
    if existing:
        if not is_untracked and staged_filename:
            for staged_item_file in (session_dir / "raw").glob(f"{item_id}_*"):
                staged_item_file.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail=f"admin.media_management.booru_import.error_duplicate:::{existing.filename}"
        )

    # Check if duplicate within this session
    for it in meta.get("items", {}).values():
        if it.get("hash") == file_hash and it.get("item_id") != item_id:
            if not is_untracked and staged_filename:
                for staged_item_file in (session_dir / "raw").glob(f"{item_id}_*"):
                    staged_item_file.unlink(missing_ok=True)
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

    phash_hex = near_duplicates.compute_item_phash_hex(file_path, file_type)

    # Generate preview thumbnail in session thumbs dir
    thumb_path = thumbs_dir / f"{item_id}{THUMBNAIL_EXT}"
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
    folder_mapping_mode_str = folder_mapping_mode if isinstance(folder_mapping_mode, str) else "use_root"
    client_date_str = client_date if isinstance(client_date, str) else None
    booru_date_str = booru_date if isinstance(booru_date, str) else None
    custom_date_str = custom_date if isinstance(custom_date, str) else None

    # Detect sibling files for metadata parsing
    sibling_files: List[Path] = []
    if is_untracked:
        if file_path.parent.exists():
            sibling_files = [p for p in file_path.parent.iterdir() if p != file_path and p.is_file()]
    else:
        raw_dir = session_dir / "raw"
        if raw_dir.exists():
            prefix = f"{item_id}_"
            sibling_files = [p for p in raw_dir.iterdir() if p != file_path and p.is_file() and p.name.startswith(prefix)]

    parser = get_parser_for_file(file_path, sibling_files)
    parsed = parser.parse(file_path, sibling_files) if parser else None
    metadata_source = parser.name if parser else None

    # Parse initial candidate tags
    candidate_tag_names: List[str] = []
    if base_tags_str:
        candidate_tag_names.extend([t.strip() for t in base_tags_str.split() if t.strip()])

    if parsed and parsed.tags:
        for pt in parsed.tags:
            if pt.name and pt.name.strip():
                candidate_tag_names.append(pt.name.strip())

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

    if parsed and parsed.tags:
        if parsed_hints is None:
            parsed_hints = {}
        for pt in parsed.tags:
            if pt.name and pt.category and pt.category != "general":
                pt_lower = pt.name.strip().lower()
                if pt_lower not in parsed_hints:
                    parsed_hints[pt_lower] = pt.category
            
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
    if not base_rating_str and parsed and parsed.rating:
        parsed_rating = RatingEnum.normalize(parsed.rating)
        if parsed_rating:
            base_rating_str = parsed_rating.value

    rating = RatingEnum.safe
    if base_rating_str:
        norm_rating = RatingEnum.normalize(base_rating_str)
        if norm_rating:
            rating = norm_rating

    # Tags resolved for a brand new item are all "added", so they may escalate its initial rating.
    escalated_initial = get_escalated_rating(rating, proposed_tags)
    if escalated_initial:
        rating = escalated_initial

    if not base_source_str and parsed and parsed.source:
        base_source_str = parsed.source

    if not base_description_str and parsed and parsed.description:
        base_description_str = parsed.description

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
            if "rating" in session_info:
                td["rating"] = session_info["rating"]
            if session_info.get("user_assigned", False):
                td["user_assigned"] = True

        tags_list.append(td)

    # Compute default relative path for untracked files
    if is_untracked and not relative_path_str:
        try:
            relative_path_str = str(file_path.resolve().relative_to(settings.ORIGINAL_DIR.resolve()))
        except Exception:
            relative_path_str = clean_filename

    # Compute suggested album path from folder mapping or parser pool names
    suggested_album_path = None
    suggested_album_segments = None
    if relative_path_str:
        fm_enabled = meta.get("folder_mapping_enabled", True)
        fm_root_mode = meta.get("folder_mapping_root_mode", folder_mapping_mode_str or "use_root")
        dummy_item = {"relative_path": relative_path_str}
        suggested_album_path = derive_item_suggested_album_path(
            dummy_item,
            meta=meta,
            enabled=fm_enabled,
            root_mode=fm_root_mode,
        )

    if not suggested_album_path and parsed and parsed.pool_names:
        suggested_album_path = parsed.pool_names[0]

    if suggested_album_path:
        suggested_album_segments = resolve_album_path(db, suggested_album_path)

    from ...utils.date_extractor import resolve_custom_date
    auto_custom_date, auto_date_origin = resolve_custom_date(
        file_path=file_path,
        booru_date=booru_date_str,
        sidecar_date=parsed.date if parsed else None,
        client_date=client_date_str,
    )

    if custom_date_str is not None and custom_date_str.strip() != "":
        resolved_custom_date, date_origin = resolve_custom_date(
            file_path=file_path,
            explicit_date=custom_date_str,
            booru_date=booru_date_str,
            sidecar_date=parsed.date if parsed else None,
            client_date=client_date_str,
        )
    else:
        resolved_custom_date, date_origin = auto_custom_date, auto_date_origin

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
        "phash": phash_hex,
        "rating": rating.value,
        "source": base_source_str or "",
        "description": base_description_str or "",
        "tags": tags_list,
        "album_ids": album_ids,
        "suggested_album_path": suggested_album_path,
        "suggested_album_segments": suggested_album_segments,
        "folder_album_removed": False,
        "folder_album_custom_path": None,
        "metadata_source": metadata_source,
        "custom_date": resolved_custom_date.isoformat(),
        "custom_date_origin": date_origin,
        "custom_date_auto": auto_custom_date.isoformat(),
        "custom_date_auto_origin": auto_date_origin,
    }

    meta.setdefault("items", {})[item_id] = item_data
    _save_session_meta(session_dir, meta)

    return item_data

@router.post("/sessions/{session_id}/files")
async def upload_files_to_session(
    session_id: str,
    file: UploadFile = File(...),
    sidecar: Optional[UploadFile] = File(None),
    relative_path: Optional[str] = Form(None),
    folder_mapping_mode: Optional[str] = Form(None),
    base_rating: Optional[str] = Form(None),
    base_source: Optional[str] = Form(None),
    base_tags: Optional[str] = Form(None),
    base_album_ids: Optional[str] = Form(None),
    category_hints: Optional[str] = Form(None),
    user_assigned_tags: Optional[str] = Form(None),
    base_description: Optional[str] = Form(None),
    client_date: Optional[str] = Form(None),
    booru_date: Optional[str] = Form(None),
    custom_date: Optional[str] = Form(None),
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

        if hasattr(sidecar, "filename") and bool(sidecar.filename) and hasattr(sidecar, "read"):
            clean_sidecar_name = Path(sidecar.filename).name
            staged_sidecar_name = f"{item_id}_{clean_sidecar_name}"
            staged_sidecar_path = raw_dir / staged_sidecar_name
            await sidecar.seek(0)
            with open(staged_sidecar_path, "wb") as f:
                while chunk := await sidecar.read(1024 * 1024):
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
            folder_mapping_mode=folder_mapping_mode,
            base_rating=base_rating,
            base_source=base_source,
            base_tags=base_tags,
            base_album_ids=base_album_ids,
            category_hints=category_hints,
            user_assigned_tags=user_assigned_tags,
            base_description=base_description,
            db=db,
            client_date=client_date,
            booru_date=booru_date,
            custom_date=custom_date,
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
            folder_mapping_mode="use_root",
            base_rating=request.base_rating,
            base_source=request.base_source,
            base_tags=request.base_tags,
            base_album_ids=request.base_album_ids,
            category_hints=request.category_hints,
            user_assigned_tags=request.user_assigned_tags,
            base_description=request.base_description,
            db=db,
            client_date=request.client_date,
            booru_date=request.booru_date,
            custom_date=request.custom_date,
        )

@router.get("/sessions/{session_id}/items/{item_id}/thumbnail")
async def get_staged_item_thumbnail(
    session_id: str,
    item_id: str,
):
    """Serve the temporary preview thumbnail of a staged item."""
    session_dir = _get_session_dir(session_id)
    thumb_path = session_dir / "thumbs" / f"{item_id}{THUMBNAIL_EXT}"
    if thumb_path.exists():
        return FileResponse(str(thumb_path), media_type=thumbnail_mime_type(thumb_path))

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
        items = meta.get("items", {})
        item = items.get(item_id)
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

        thumb_path = session_dir / "thumbs" / f"{item_id}{THUMBNAIL_EXT}"
        generate_thumbnail(media_path, thumb_path, item["file_type"])

        if not near_duplicates.phash_from_hex(item.get("phash")):
            item["phash"] = near_duplicates.compute_item_phash_hex(media_path, item["file_type"])

        # Re-evaluate current tags with DB
        current_tag_names = [t["name"] for t in item.get("tags", []) if t.get("name")]
        pre_implied_map = {
            t["name"].strip().lower(): (t.get("implied_by") or [])
            for t in item.get("tags", [])
            if t.get("name") and t.get("implied")
        }
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
            pre_implied_map=pre_implied_map,
        )
        item["tags"] = [t.model_dump() if hasattr(t, "model_dump") else dict(t) for t in proposed_tags]

        meta["items"][item_id] = item
        _save_session_meta(session_dir, meta)

        return item
