import uuid
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session
from ...auth import require_admin_mode
from ...database import get_db
from ...models import Media, User
from ...schemas import ShareSettingsUpdate
from ...utils.cache import invalidate_media_item_cache
from ...utils.format_registry import format_registry
from ...utils.logger import logger
from ...utils.media_helpers import (
    create_stripped_media_cache,
    delete_media_cache,
    get_effective_media_path,
    rebuild_stripped_cache_if_needed,
)

router = APIRouter()

@router.post("/{media_id}/share")
async def share_media(
    media_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Create or update share link for media"""
    from fastapi import Query

    from ...database import get_db
    
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    if not media.is_shared:
        import uuid
        media.share_uuid = str(uuid.uuid4())
        media.is_shared = True
        
        # Trigger background stripping if AI metadata not shared
        if not getattr(media, "share_ai_metadata", False):
            effective_path = get_effective_media_path(media)
            effective_mime = format_registry.get_mime_type(effective_path.name, default=media.mime_type)
            if effective_mime and effective_mime.startswith('image/'):
                background_tasks.add_task(create_stripped_media_cache, media, effective_mime)
    
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
        delete_media_cache(media)
    except Exception as e:
        logger.error(f"Failed to cleanup cache for unshared media: {e}")
    
    return {"message": "Share removed"}

@router.patch("/{media_id}/share-settings")
async def update_share_settings(
    media_id: int,
    updates: ShareSettingsUpdate,
    background_tasks: BackgroundTasks = None,
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
        changed = updates.share_ai_metadata != media.share_ai_metadata
        if changed:
            media.share_ai_metadata = updates.share_ai_metadata
            delete_media_cache(media)
        if not media.share_ai_metadata:
            await rebuild_stripped_cache_if_needed(media, background_tasks)
        
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
