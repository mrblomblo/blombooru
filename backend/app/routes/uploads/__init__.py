from fastapi import APIRouter

from ...schemas import ProposedTag, UploadSessionItemUpdate
from .commit import (
    commit_upload_session,
    router as _commit_router,
)
from .items import (
    BulkUpdateRequest,
    bulk_update_staged_items,
    delete_staged_item,
    router as _items_router,
    update_staged_item,
)
from .pending import (
    get_pending_entities,
    router as _pending_router,
    update_folder_mapping,
    update_pending_album,
    update_pending_tag,
)
from .session_store import (
    UPLOAD_SESSIONS_DIR,
    _get_session_dir,
    _get_session_lock,
    _get_session_pending_tags_map,
    _load_session_meta,
    _save_session_meta,
    _session_locks,
    cancel_upload_session,
    cleanup_upload_sessions,
    create_upload_session,
    get_session_near_duplicates,
    get_upload_session,
    router as _session_store_router,
)
from .staging import (
    _process_and_stage_item,
    add_untracked_file_to_session,
    analyze_staged_item,
    get_staged_item_file,
    get_staged_item_thumbnail,
    router as _staging_router,
    upload_files_to_session,
)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

router.include_router(_session_store_router)
router.include_router(_staging_router)
router.include_router(_items_router)
router.include_router(_pending_router)
router.include_router(_commit_router)

__all__ = [
    "BulkUpdateRequest",
    "ProposedTag",
    "UPLOAD_SESSIONS_DIR",
    "UploadSessionItemUpdate",
    "_get_session_dir",
    "_get_session_lock",
    "_get_session_pending_tags_map",
    "_load_session_meta",
    "_process_and_stage_item",
    "_save_session_meta",
    "_session_locks",
    "add_untracked_file_to_session",
    "analyze_staged_item",
    "bulk_update_staged_items",
    "cancel_upload_session",
    "cleanup_upload_sessions",
    "commit_upload_session",
    "create_upload_session",
    "delete_staged_item",
    "get_pending_entities",
    "get_session_near_duplicates",
    "get_staged_item_file",
    "get_staged_item_thumbnail",
    "get_upload_session",
    "router",
    "update_folder_mapping",
    "update_pending_album",
    "update_pending_tag",
    "update_staged_item",
    "upload_files_to_session",
]
