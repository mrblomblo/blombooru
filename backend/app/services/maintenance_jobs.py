import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import HTTPException

from ..utils.logger import logger

class MaintenanceJobManager:
    """Thread-safe registry for long-running admin maintenance jobs."""

    def __init__(self) -> None:
        self._registry_lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._state_locks: Dict[str, threading.Lock] = {}
        self._default_exec_locks: Dict[str, threading.Lock] = {}
        self._initial_fields: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        job_name: str,
        initial_fields: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a maintenance job so its idle status is always queryable."""
        fields = dict(initial_fields or {})
        with self._registry_lock:
            if job_name not in self._jobs:
                self._state_locks[job_name] = threading.Lock()
                self._default_exec_locks[job_name] = threading.Lock()
                self._initial_fields[job_name] = fields
                self._jobs[job_name] = {
                    "running": False,
                    "current": 0,
                    "total": 0,
                    "current_file": None,
                    "error": None,
                    "result": None,
                    "started_at": None,
                    "finished_at": None,
                    **fields,
                }

    def _ensure_registered(self, job_name: str) -> None:
        if job_name not in self._jobs:
            self.register(job_name)

    def get_status(self, job_name: str, include_result: bool = True) -> Optional[Dict[str, Any]]:
        """Return a snapshot of a job's status, or None if unknown."""
        with self._registry_lock:
            state_lock = self._state_locks.get(job_name)
            state = self._jobs.get(job_name)
        if state_lock is None or state is None:
            return None
        with state_lock:
            snapshot = dict(state)
        if not include_result:
            snapshot.pop("result", None)
        return snapshot

    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Return summary snapshots (without large result payloads) for all jobs."""
        with self._registry_lock:
            names = list(self._jobs.keys())
        summaries: Dict[str, Dict[str, Any]] = {}
        for name in names:
            snap = self.get_status(name, include_result=False)
            if snap is not None:
                summaries[name] = snap
        return summaries

    def start_job(
        self,
        job_name: str,
        worker_fn: Callable[[Callable[..., None]], Any],
        execution_lock: Optional[threading.Lock] = None,
        initial_fields: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Start a maintenance job in a daemon thread."""
        self._ensure_registered(job_name)
        with self._registry_lock:
            state_lock = self._state_locks[job_name]
            state = self._jobs[job_name]
            exec_lock = execution_lock or self._default_exec_locks[job_name]
            reset_fields = dict(
                initial_fields if initial_fields is not None else self._initial_fields.get(job_name, {})
            )

        if not exec_lock.acquire(blocking=False):
            with state_lock:
                already_running = bool(state.get("running"))
            if already_running:
                return False, self.get_status(job_name, include_result=False) or {}
            raise HTTPException(status_code=409, detail="common.processing")

        with state_lock:
            state.update(
                {
                    "running": True,
                    "current": 0,
                    "total": 0,
                    "current_file": None,
                    "error": None,
                    "result": None,
                    "started_at": time.time(),
                    "finished_at": None,
                    **reset_fields,
                }
            )

        def update_progress(**kwargs: Any) -> None:
            with state_lock:
                state.update(kwargs)

        def runner() -> None:
            try:
                result = worker_fn(update_progress)
                with state_lock:
                    state["result"] = result
            except Exception as e:
                logger.error(f"Error in background maintenance job '{job_name}': {e}", exc_info=True)
                with state_lock:
                    state["error"] = str(e)
            finally:
                with state_lock:
                    state["running"] = False
                    state["current_file"] = None
                    state["finished_at"] = time.time()
                exec_lock.release()

        try:
            thread = threading.Thread(target=runner, daemon=True)
            thread.start()
        except Exception:
            with state_lock:
                state["running"] = False
                state["current_file"] = None
                state["finished_at"] = time.time()
            exec_lock.release()
            raise

        return True, self.get_status(job_name, include_result=False) or {}

maintenance_jobs = MaintenanceJobManager()

# Pre-register all maintenance jobs so status queries work before first run.
maintenance_jobs.register(
    "generate_missing_thumbnails",
    {"orphans_deleted": 0, "generated": 0, "failed": 0, "skipped": 0},
)
maintenance_jobs.register(
    "regenerate_all_thumbnails",
    {"deleted": 0, "generated": 0, "failed": 0},
)
maintenance_jobs.register(
    "relink_media",
    {"relinked": 0, "unresolved": 0},
)
maintenance_jobs.register("apply_aliases")
maintenance_jobs.register("apply_implications")
maintenance_jobs.register(
    "backfill_implied_tags",
    {"updated_media": 0, "updated_tags": 0},
)
maintenance_jobs.register("apply_tag_ratings")
maintenance_jobs.register("recalculate_album_metrics")
maintenance_jobs.register("prune_albums")
