from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, case, desc, func, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin_mode
from ..database import get_db
from ..models import Media, Tag, User, blombooru_media_tags
from ..schemas import TagCategoryEnum, TagCreate, TagResponse
from ..utils.cache import cache_response, invalidate_tag_cache

router = APIRouter(prefix="/api/tags", tags=["tags"])

@router.get("/", response_model=List[TagResponse])
@router.get("", response_model=List[TagResponse])
@cache_response(expire=3600, key_prefix="tags")
async def get_tags(
    request: Request,
    search: Optional[str] = None,
    names: Optional[str] = Query(None, description="Comma-separated list of tag names"),
    category: Optional[TagCategoryEnum] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get tags with optional filtering"""
    query = db.query(Tag)
    
    if names:
        tag_names = [n.strip().lower() for n in names.split(",") if n.strip()]
        if tag_names:
            query = query.filter(Tag.name.in_(tag_names))
            limit = max(limit, len(tag_names))
            tags = query.all()
            name_map = {t.name: t for t in tags}
            return [name_map[n] for n in tag_names if n in name_map]
    
    if search:
        query = query.filter(Tag.name.ilike(f"%{search}%"))
    
    if category:
        query = query.filter(Tag.category == category)
    
    query = query.order_by(desc(Tag.post_count))
    tags = query.limit(limit).all()
    
    return tags

@router.get("/autocomplete")
@cache_response(expire=3600, key_prefix="autocomplete")
async def autocomplete_tags(
    request: Request,
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db)
):
    """Autocomplete tag suggestions (includes shared tags if enabled)"""
    from ..database import get_shared_db, is_shared_db_available
    from ..models import TagAlias
    from ..services.shared_tags import SharedTagService

    # If shared tags enabled, use merged autocomplete
    if is_shared_db_available():
        shared_db_gen = get_shared_db()
        shared_db = next(shared_db_gen, None)
        try:
            service = SharedTagService(db, shared_db)
            return service.autocomplete_merged(q, limit=50)
        finally:
            if shared_db:
                try:
                    next(shared_db_gen, None)
                except StopIteration:
                    pass
    
    # Fall back to local-only autocomplete
    alias = db.query(TagAlias).filter(TagAlias.alias_name.ilike(q)).first()
    
    if alias:
        target_tag = db.query(Tag).filter(Tag.id == alias.target_tag_id).first()
        if target_tag:
            return [{
                "name": target_tag.name,
                "category": target_tag.category,
                "count": target_tag.post_count,
                "is_alias": True,
                "alias_name": q.lower()
            }]
    
    priority = case(
        (Tag.name.ilike(f"{q}%"), 1),
        else_=2
    )
    
    tags = db.query(Tag).filter(
        Tag.name.ilike(f"%{q}%")
    ).order_by(priority, desc(Tag.post_count)).limit(50).all()
    
    return [{"name": tag.name, "category": tag.category, "count": tag.post_count} for tag in tags]

@router.get("/{tag_name}", response_model=TagResponse)
@cache_response(expire=3600, key_prefix="tag_detail")
async def get_tag(request: Request, tag_name: str, db: Session = Depends(get_db)):
    """Get single tag"""
    tag = db.query(Tag).filter(Tag.name == tag_name.lower()).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag

@router.post("/", response_model=TagResponse)
async def create_tag(
    tag_data: TagCreate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Create new tag"""
    existing = db.query(Tag).filter(Tag.name == tag_data.name.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tag already exists")
    
    tag = Tag(
        name=tag_data.name.lower(),
        category=tag_data.category
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    invalidate_tag_cache()
    
    return tag

@router.patch("/{tag_id}")
async def update_tag(
    tag_id: int,
    category: TagCategoryEnum,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Update tag category"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    tag.category = category
    db.commit()
    invalidate_tag_cache()
    
    return {"message": "Tag updated successfully"}

@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Delete tag"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    tag_name = tag.name  # Save name before deletion
    
    db.delete(tag)
    db.commit()
    invalidate_tag_cache()
    
    # Also delete from shared database if enabled
    from ..config import settings
    if settings.SHARED_TAGS_ENABLED:
        from ..database import get_shared_db, is_shared_db_available
        if is_shared_db_available():
            shared_db_gen = get_shared_db()
            shared_db = next(shared_db_gen, None)
            if shared_db:
                try:
                    from ..services.shared_tags import SharedTagService
                    service = SharedTagService(db, shared_db)
                    service.delete_from_shared(tag_name)
                finally:
                    try:
                        next(shared_db_gen, None)
                    except StopIteration:
                        pass
    
    return {"message": "Tag deleted successfully"}

@router.get("/{tag_name}/related")
@cache_response(expire=3600, key_prefix="tag_detail")
async def get_related_tags(
    request: Request,
    tag_name: str,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get tags that frequently appear with this tag"""
    tag = db.query(Tag).filter(Tag.name == tag_name.lower()).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    media_with_tag = db.query(Media.id).join(blombooru_media_tags).filter(
        blombooru_media_tags.c.tag_id == tag.id
    ).subquery()
    
    related = db.query(
        Tag,
        func.count(blombooru_media_tags.c.media_id).label('cooccurrence')
    ).join(blombooru_media_tags).filter(
        blombooru_media_tags.c.media_id.in_(media_with_tag),
        Tag.id != tag.id
    ).group_by(Tag.id).order_by(desc('cooccurrence')).limit(limit).all()
    
    return [
        {
            "name": t.name,
            "category": t.category,
            "count": t.post_count,
            "cooccurrence": co
        }
        for t, co in related
    ]

@router.get("/related")
@cache_response(expire=3600, key_prefix="tag_detail")
async def related_tags(
    request: Request,
    tags: str = Query(...),
    db: Session = Depends(get_db)
):
    tag_list = [t.strip() for t in tags.split(',') if t.strip()]
    if not tag_list:
        return []

    subquery = db.query(
        Media.id
    ).join(
        blombooru_media_tags
    ).join(
        Tag
    ).filter(
        Tag.name.in_(tag_list)
    ).subquery()

    related = db.query(
        Tag,
        func.count(blombooru_media_tags.c.media_id).label('frequency')
    ).join(
        blombooru_media_tags
    ).filter(
        and_(
            blombooru_media_tags.c.media_id.in_(subquery),
            ~Tag.name.in_(tag_list)  # Exclude input tags
        )
    ).group_by(
        Tag.id
    ).order_by(
        desc('frequency')
    ).limit(20).all()

    return [{
        "id": tag.id,
        "name": tag.name,
        "category": tag.category,
        "frequency": freq
    } for tag, freq in related]
