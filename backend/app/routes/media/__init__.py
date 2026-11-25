from fastapi import APIRouter

from .chunked import (
    ARCHIVE_CHUNKS_DIR,
    MAX_CHUNK_SIZE,
    MEDIA_CHUNKS_DIR,
    cleanup_archive,
    cleanup_archive_chunks,
    cleanup_media_chunks,
    extract_archive,
    finalize_chunked_upload,
    get_archive_file,
    router as _chunked_router,
    upload_archive_chunk,
    upload_media_chunk,
)
from .crud import (
    DescriptionPreviewRequest,
    DescriptionPreviewResponse,
    clear_media_children_order,
    delete_media,
    get_media,
    get_media_file,
    get_media_metadata,
    get_media_thumbnail,
    preview_media_description,
    reorder_media_children,
    router as _crud_router,
    update_media,
    upload_media,
)
from .ingestion import (
    process_and_save_media,
    sync_description_enlarged,
)
from .listing import (
    BATCH_CHUNK_SIZE,
    _fetch_media_batch_full,
    _fetch_media_batch_info,
    _fetch_media_batch_tags_only,
    bulk_update_metadata,
    bulk_update_ratings,
    bulk_update_tags,
    get_media_batch,
    get_media_list,
    post_media_batch,
    post_media_batch_metadata,
    post_media_batch_scan_dates,
    router as _listing_router,
)
from .navigation import (
    _build_album_media_id_query,
    get_adjacent_media,
    get_media_album_context,
    get_media_albums,
    get_related_media,
    router as _navigation_router,
)
from .sharing import (
    router as _sharing_router,
    share_media,
    unshare_media,
    update_share_settings,
)
from .tags import (
    _clean_implied_by_groups,
    _normalize_db_implied_by_ids,
    apply_media_tag_implications,
    get_or_create_tags,
    get_or_create_tags_with_implications,
    preview_or_create_tags,
    resolve_media_tag_update,
    update_tag_counts,
)
from .update_source import (
    PostUpdateRequest,
    StagedFileRef,
    _resolve_staged_file,
    router as _update_source_router,
    update_file_finalize,
    update_from_source,
)

router = APIRouter(prefix="/api/media", tags=["media"])

# Static paths must be registered before dynamic /{media_id} routes
router.add_api_route("", get_media_list, methods=["GET"])
router.include_router(_listing_router)
router.include_router(_chunked_router)
router.include_router(_update_source_router)
router.include_router(_navigation_router)
router.include_router(_sharing_router)
router.include_router(_crud_router)

__all__ = [
    "ARCHIVE_CHUNKS_DIR",
    "BATCH_CHUNK_SIZE",
    "DescriptionPreviewRequest",
    "DescriptionPreviewResponse",
    "MAX_CHUNK_SIZE",
    "MEDIA_CHUNKS_DIR",
    "PostUpdateRequest",
    "StagedFileRef",
    "_build_album_media_id_query",
    "_clean_implied_by_groups",
    "_fetch_media_batch_full",
    "_fetch_media_batch_info",
    "_fetch_media_batch_tags_only",
    "_normalize_db_implied_by_ids",
    "_resolve_staged_file",
    "apply_media_tag_implications",
    "bulk_update_metadata",
    "bulk_update_ratings",
    "bulk_update_tags",
    "cleanup_archive",
    "cleanup_archive_chunks",
    "cleanup_media_chunks",
    "clear_media_children_order",
    "delete_media",
    "extract_archive",
    "finalize_chunked_upload",
    "get_adjacent_media",
    "get_archive_file",
    "get_media",
    "get_media_album_context",
    "get_media_albums",
    "get_media_batch",
    "get_media_file",
    "get_media_list",
    "get_media_metadata",
    "get_media_thumbnail",
    "get_or_create_tags",
    "get_or_create_tags_with_implications",
    "get_related_media",
    "post_media_batch",
    "post_media_batch_metadata",
    "post_media_batch_scan_dates",
    "preview_media_description",
    "preview_or_create_tags",
    "process_and_save_media",
    "reorder_media_children",
    "resolve_media_tag_update",
    "router",
    "share_media",
    "sync_description_enlarged",
    "unshare_media",
    "update_file_finalize",
    "update_from_source",
    "update_media",
    "update_share_settings",
    "update_tag_counts",
    "upload_archive_chunk",
    "upload_media",
    "upload_media_chunk",
]
