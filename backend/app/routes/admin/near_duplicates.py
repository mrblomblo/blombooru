import asyncio
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...auth import require_admin_mode
from ...config import settings
from ... import database
from ...database import get_db
from ...models import User
from ...utils.logger import logger
from ...services import near_duplicates

router = APIRouter()

class NearDuplicateSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    max_distance: Optional[int] = Field(default=None, ge=0, le=64)

def start_backfill_task() -> bool:
    """Start background PDQ hashing all hashable posts (no-op if already running)."""
    status = near_duplicates.get_backfill_status()
    if status["running"]:
        return False
    session_factory = database.SessionLocal
    if session_factory is None:
        logger.debug("Near-duplicate backfill not started: database is not initialised yet")
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("Near-duplicate backfill not started: no running event loop")
        return False
    near_duplicates.mark_backfill_queued()
    loop.create_task(asyncio.to_thread(near_duplicates.backfill_missing_phashes, session_factory))
    return True

def _count_pending(db: Session) -> int:
    return near_duplicates.count_unhashed(db)

@router.get("/near-duplicates")
async def get_near_duplicate_settings(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Current near-duplicate settings plus hashing progress."""
    return {
        **settings.NEAR_DUPLICATE_SETTINGS,
        "pending": _count_pending(db),
        "backfill": near_duplicates.get_backfill_status(),
    }

@router.put("/near-duplicates")
async def update_near_duplicate_settings(
    data: NearDuplicateSettingsUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Update near-duplicate settings."""
    current = dict(settings.NEAR_DUPLICATE_SETTINGS)
    if data.enabled is not None:
        current["enabled"] = data.enabled
    if data.max_distance is not None:
        current["max_distance"] = data.max_distance
    settings.save_settings({"near_duplicates": current})

    return {
        **settings.NEAR_DUPLICATE_SETTINGS,
        "pending": _count_pending(db),
        "backfill": near_duplicates.get_backfill_status(),
        "backfill_started": False,
        "message_key": "notifications.admin.settings_updated",
    }

@router.post("/near-duplicates/backfill")
async def start_near_duplicate_backfill(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Hash or re-hash all existing hashable posts."""
    started = start_backfill_task()
    return {
        "started": started,
        "pending": _count_pending(db),
        "backfill": near_duplicates.get_backfill_status(),
    }
