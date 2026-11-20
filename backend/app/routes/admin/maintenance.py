from fastapi import APIRouter, Depends, HTTPException

from ...auth import require_admin_mode
from ...models import User
from ...services import near_duplicates
from ...services.maintenance_jobs import maintenance_jobs
from .media import _transcode_status

router = APIRouter()

@router.get("/maintenance/status")
async def get_all_maintenance_statuses(
    current_user: User = Depends(require_admin_mode),
):
    """Return summary status for all admin maintenance jobs."""
    jobs = maintenance_jobs.get_all_statuses()
    transcode_summary = dict(_transcode_status)
    transcode_summary.pop("last_result", None)
    jobs["transcode_media"] = transcode_summary
    jobs["near_duplicate_backfill"] = near_duplicates.get_backfill_status()
    return {"jobs": jobs}

@router.get("/maintenance/status/{job_name}")
async def get_maintenance_job_status(
    job_name: str,
    current_user: User = Depends(require_admin_mode),
):
    """Return detailed status (including result) for a single maintenance job."""
    if job_name == "transcode_media":
        return dict(_transcode_status)
    if job_name == "near_duplicate_backfill":
        return near_duplicates.get_backfill_status()

    status = maintenance_jobs.get_status(job_name, include_result=True)
    if status is None:
        raise HTTPException(status_code=404, detail="Unknown maintenance job")
    return status
