import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...auth import require_admin_mode
from ...config import settings
from ...database import get_db
from ...models import Tag, TagAlias, User

router = APIRouter()

@router.post("/test-shared-tag-db")
async def test_shared_tag_db(data: dict, current_user: User = Depends(require_admin_mode)):
    """Test shared tag database connection"""
    try:
        host = data.get('host', 'shared-tag-db')
        port = data.get('port', 5432)
        name = data.get('name', 'shared_tags')
        user = data.get('user', 'postgres')
        password = data.get('password', '')
        
        if password == "***":
            password = settings.SHARED_TAG_DB_PASSWORD
        
        test_url = f"postgresql://{user}:{password}@{host}:{port}/{name}"
        
        test_engine = sqlalchemy_create_engine(
            test_url, 
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5}
        )
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        test_engine.dispose()
        
        return {"success": True, "message": "Connection successful"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@router.get("/shared-tags/status")
async def get_shared_tags_status(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Get shared tag database status"""
    from ...database import (get_shared_db, get_shared_db_error,
                            is_shared_db_available)
    
    status = {
        "enabled": settings.SHARED_TAGS_ENABLED,
        "connected": is_shared_db_available(),
        "error": get_shared_db_error() if not is_shared_db_available() else None,
        "config": {
            "host": settings.SHARED_TAG_DB_HOST,
            "port": settings.SHARED_TAG_DB_PORT,
            "name": settings.SHARED_TAG_DB_NAME,
            "user": settings.SHARED_TAG_DB_USER
        }
    }
    
    status["local_tags"] = db.query(Tag).count()
    status["local_aliases"] = db.query(TagAlias).count()
    
    if is_shared_db_available():
        shared_db_gen = get_shared_db()
        shared_db = next(shared_db_gen, None)
        try:
            if shared_db:
                from ...shared_tag_models import SharedTag, SharedTagAlias
                status["shared_tags"] = shared_db.query(SharedTag).count()
                status["shared_aliases"] = shared_db.query(SharedTagAlias).count()
        finally:
            if shared_db:
                try:
                    next(shared_db_gen, None)
                except StopIteration:
                    pass
    
    return status

@router.post("/shared-tags/sync")
async def sync_shared_tags(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Trigger manual sync with shared tag database"""
    from ...database import (get_shared_db, is_shared_db_available,
                            reconnect_shared_db)
    from ...services.shared_tags import SharedTagService
    from ...utils.cache import invalidate_tag_cache
    
    if not settings.SHARED_TAGS_ENABLED:
        raise HTTPException(status_code=400, detail="Shared tags not enabled")
    
    if not is_shared_db_available():
        reconnect_shared_db()
        
    if not is_shared_db_available():
        raise HTTPException(status_code=503, detail="Shared tag database not available")
    
    shared_db_gen = get_shared_db()
    shared_db = next(shared_db_gen, None)
    
    try:
        if not shared_db:
            raise HTTPException(status_code=503, detail="Could not get shared database session")
        
        service = SharedTagService(db, shared_db)
        result = await asyncio.to_thread(service.full_sync)
        invalidate_tag_cache()
        
        return {
            "success": len(result.errors) == 0,
            "tags_imported": result.tags_imported,
            "tags_exported": result.tags_exported,
            "aliases_imported": result.aliases_imported,
            "aliases_exported": result.aliases_exported,
            "conflicts_resolved": result.conflicts_resolved,
            "errors": result.errors
        }
    finally:
        if shared_db:
            try:
                next(shared_db_gen, None)
            except StopIteration:
                pass

@router.post("/shared-tags/reconnect")
async def reconnect_shared_tags(
    current_user: User = Depends(require_admin_mode)
):
    """Attempt to reconnect to the shared tag database"""
    from ...database import (get_shared_db_error, init_shared_db,
                            is_shared_db_available, reconnect_shared_db)
    
    if not settings.SHARED_TAGS_ENABLED:
        raise HTTPException(status_code=400, detail="Shared tags not enabled")
    
    reconnect_shared_db()
    
    if is_shared_db_available():
        init_shared_db()
        return {"success": True, "message": "Reconnected successfully"}
    else:
        return {"success": False, "message": get_shared_db_error()}
