from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, asc, case, desc, func, or_
from sqlalchemy.orm import Session

from ..auth import require_admin_mode
from ..config import settings
from ..database import get_db
from ..models import Media, RatingEnum, Tag, User, blombooru_media_tags
from ..schemas import TagCategoryEnum, TagCreate, TagResponse
from ..utils.cache import cache_response, invalidate_tag_cache
from ..utils.search_parser import apply_search_criteria, parse_search_query

router = APIRouter(prefix="/api/tags", tags=["tags"])

def get_effective_limit(limit: Optional[int]) -> int:
    if limit is None or limit <= 0:
        return settings.get_items_per_page()
    return limit

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

@router.get("/list", response_model=dict)
@router.get("/list/", response_model=dict)
@cache_response(expire=3600, key_prefix="tags_list")
async def get_tags_list(
    request: Request,
    page: int = 1,
    limit: Optional[int] = Query(default=None),
    sort: Optional[str] = Query(default="post_count"),
    order: Optional[str] = Query(default="desc"),
    db: Session = Depends(get_db)
):
    """Get paginated tag list"""
    limit = get_effective_limit(limit)

    # Build query
    query = db.query(Tag)

    # Apply Sorting
    sort_column = Tag.post_count
    if sort == "tag_name":
        sort_column = Tag.name
    elif sort == "category":
        sort_column = Tag.category
    elif sort == "created_at":
        sort_column = Tag.created_at

    # Apply Sorting Order
    if order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))

    # Get All Tags
    total_tags = query.count()
    page_start = (page - 1) * limit
    paginated_tags = query.offset(page_start).limit(limit).all()

    # Build Response
    return_items = []
    for tag in paginated_tags:
        return_items.append(TagResponse(
            name=tag.name,
            category=tag.category,
            id=tag.id,
            post_count=tag.post_count,
            created_at=tag.created_at
        ))

    return {
        "items": return_items,
        "total": total_tags,
        "page": page,
        "limit": limit,
        "pages": max(1, (total_tags + limit - 1) // limit)
    }

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
    
    priority = case(
        (Tag.name.ilike(f"{q}%"), 1),
        else_=2
    )
    
    tags = db.query(Tag).filter(
        Tag.name.ilike(f"%{q}%")
    ).order_by(priority, desc(Tag.post_count)).limit(50).all()
    
    seen_tags = {tag.name for tag in tags}
    results = [
        {"name": tag.name, "category": tag.category, "count": tag.post_count}
        for tag in tags
    ]
    
    if len(results) < 50:
        aliases = (
            db.query(TagAlias)
            .filter(TagAlias.alias_name.ilike(f"{q}%"))
            .limit(50 - len(results))
            .all()
        )
        for alias in aliases:
            target = db.query(Tag).filter(Tag.id == alias.target_tag_id).first()
            if target and target.name not in seen_tags:
                results.append({
                    "name": target.name,
                    "category": target.category,
                    "count": target.post_count,
                    "is_alias": True,
                    "alias_name": alias.alias_name.lower()
                })
                seen_tags.add(target.name)
    
    return results

@router.get("/search-related")
@cache_response(expire=300, key_prefix="search_related")
async def search_related_tags(
    request: Request,
    q: str = Query(default="", description="Search query string"),
    rating: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get tags most commonly co-occurring with the given search query results."""
    if not q or not q.strip():
        return []

    parsed = parse_search_query(q)

    # Build media subquery using the full search pipeline
    media_query = db.query(Media.id)
    media_query = apply_search_criteria(media_query, parsed, db)

    # Apply top-level rating filter (separate from query string rating: meta)
    if rating and rating.lower() != "explicit":
        allowed_ratings = {
            "safe": [RatingEnum.safe],
            "questionable": [RatingEnum.safe, RatingEnum.questionable]
        }
        media_query = media_query.filter(Media.rating.in_(allowed_ratings.get(rating.lower(), [])))

    media_subquery = media_query.subquery()

    # Non-negated, non-wildcard tag names to exclude
    excluded_tag_names = [name.lower() for name in parsed["tags"]["include"]]

    cooccurrence_query = (
        db.query(
            Tag,
            func.count(blombooru_media_tags.c.media_id).label("frequency"),
        )
        .join(blombooru_media_tags, blombooru_media_tags.c.tag_id == Tag.id)
        .filter(blombooru_media_tags.c.media_id.in_(media_subquery))
        .group_by(Tag.id)
        .order_by(desc("frequency"))
        .limit(limit + len(excluded_tag_names))  # over-fetch to allow exclusion
    )

    results = cooccurrence_query.all()

    return [
        {
            "name": tag.name,
            "category": tag.category,
            "count": tag.post_count,
            "frequency": frequency,
        }
        for tag, frequency in results
        if tag.name.lower() not in excluded_tag_names
    ][:limit]

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
