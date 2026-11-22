import asyncio
import json
import shutil
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...auth import require_admin_mode
from ...config import settings
from ...database import get_db
from ...models import User
from ...services import near_duplicates
from ...utils.logger import logger

router = APIRouter()

UPLOAD_SESSIONS_DIR = settings.CACHE_DIR / "upload-sessions"
UPLOAD_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

def _get_upload_sessions_dir() -> Path:
    import sys
    pkg = sys.modules.get(__package__)
    if pkg is not None and hasattr(pkg, "UPLOAD_SESSIONS_DIR"):
        return pkg.UPLOAD_SESSIONS_DIR
    return UPLOAD_SESSIONS_DIR

_session_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

def _get_session_lock(session_id: str) -> asyncio.Lock:
    safe_id = Path(session_id).name
    return _session_locks[safe_id]

def cleanup_upload_sessions(max_age_seconds: int = 3600):
    """Clean up upload session directories older than max_age_seconds."""
    if not _get_upload_sessions_dir().exists():
        return
    cutoff = time.time() - max_age_seconds
    for session_dir in _get_upload_sessions_dir().iterdir():
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
    session_dir = _get_upload_sessions_dir() / safe_id
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
                rat = t.get("rating", "none")
                user_assigned = t.get("user_assigned", False)
                if name not in tag_map:
                    tag_map[name] = {"category": cat, "rating": rat, "user_assigned": user_assigned}
                else:
                    if user_assigned:
                        tag_map[name]["category"] = cat
                        tag_map[name]["rating"] = rat
                        tag_map[name]["user_assigned"] = True
    return tag_map

@router.post("/sessions")
async def create_upload_session(
    current_user: User = Depends(require_admin_mode),
):
    """Create a new staging session for confirmation-first upload review."""
    session_id = str(uuid.uuid4())
    session_dir = _get_upload_sessions_dir() / session_id
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

@router.get("/sessions/{session_id}/near-duplicates")
async def get_session_near_duplicates(
    session_id: str,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Report near-duplicates (perceptually similar media) for every item in the session."""
    session_dir = _get_session_dir(session_id)
    meta = _load_session_meta(session_dir)
    items = meta.get("items", {})

    max_distance = near_duplicates.get_max_distance()
    response = {
        "enabled": near_duplicates.is_enabled(),
        "max_distance": max_distance,
        "items": {},
    }
    if not response["enabled"]:
        return response

    queue_matches = near_duplicates.find_queue_matches(items, max_distance)
    for item_id, item in items.items():
        phash_value = near_duplicates.phash_from_hex(item.get("phash"))
        existing = near_duplicates.find_existing_matches(db, phash_value, max_distance)
        queue = queue_matches.get(item_id, [])
        if existing or queue:
            response["items"][item_id] = {"existing": existing, "queue": queue}
    return response

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
