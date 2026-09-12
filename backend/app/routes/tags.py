from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, asc, case, desc, func, or_
from sqlalchemy.orm import Session

from ..auth import require_admin_mode
from ..config import settings
from ..database import get_db
from ..models import Media, RatingEnum, Tag, TagAlias, User, blombooru_media_tags
from ..schemas import (BatchResolveCombinedRequest,
                       BatchResolveCombinedResponse, BatchTagValidateRequest,
                       TagCategoryEnum, TagCreate, TagResponse)
from ..utils.cache import cache_response, invalidate_tag_cache
from ..utils.search_parser import (apply_custom_filters_or,
                                   apply_search_criteria, parse_search_query)

router = APIRouter(prefix="/api/tags", tags=["tags"])

def get_effective_limit(limit: Optional[int]) -> int:
    if limit is None or not isinstance(limit, int) or limit <= 0:
        return settings.get_items_per_page()
    return limit

@router.post("/batch-validate")
async def batch_validate_tags(
    payload: BatchTagValidateRequest,
    db: Session = Depends(get_db)
):
    """Validate a batch of tag names, resolving aliases and checking existence."""
    from ..utils.tag_utils import resolve_aliases

    raw_names = [n.strip().lower() for n in payload.names if n and n.strip()]
    if not raw_names:
        return {"resolved": {}}

    unique_names = list(set(raw_names))
    alias_map = resolve_aliases(db, unique_names)

    resolved_names_to_check = set()
    for name in unique_names:
        if name in alias_map:
            resolved_names_to_check.add(alias_map[name][0].lower())
        else:
            resolved_names_to_check.add(name)

    existing_tags = {}
    CHUNK_SIZE = 500
    chk_list = list(resolved_names_to_check)
    for i in range(0, len(chk_list), CHUNK_SIZE):
        chunk = chk_list[i:i + CHUNK_SIZE]
        tags = db.query(Tag.name, Tag.category).filter(Tag.name.in_(chunk)).all()
        for t in tags:
            existing_tags[t.name.lower()] = {"name": t.name, "category": t.category.value if t.category else 'general'}

    results = {}
    for name in unique_names:
        if name in alias_map:
            target_name = alias_map[name][0]
            if target_name.lower() in existing_tags:
                results[name] = existing_tags[target_name.lower()]
            else:
                results[name] = {"name": target_name, "category": None}
        elif name in existing_tags:
            results[name] = existing_tags[name]
        else:
            results[name] = None

    return {"resolved": results}

@router.post("/batch-resolve-combined", response_model=BatchResolveCombinedResponse)
async def batch_resolve_combined_tags(
    payload: BatchResolveCombinedRequest,
    db: Session = Depends(get_db)
):
    """Resolve aliases and expand implications on the combined set of current + new tags for each item."""
    from ..utils.tag_utils import resolve_aliases, resolve_implications

    if not payload.items:
        return {"results": {}, "alias_resolutions": {}}

    # 1. Collect all raw tag names across all items to resolve aliases in batch
    all_raw_tags = set()
    for item in payload.items:
        for t in item.current_tags:
            clean = t.strip()
            if clean:
                all_raw_tags.add(clean.lower())
                all_raw_tags.add(clean.replace(" ", "_").lower())
        for t in item.new_tags:
            clean = t.strip()
            if clean:
                all_raw_tags.add(clean.lower())
                all_raw_tags.add(clean.replace(" ", "_").lower())

    alias_map = resolve_aliases(db, list(all_raw_tags))

    # 2. Collect canonical names to query existing tags for correct database casing
    all_canonical_names = set()
    for raw in all_raw_tags:
        if raw in alias_map:
            all_canonical_names.add(alias_map[raw][0].lower())
        else:
            all_canonical_names.add(raw)

    existing_tags_by_name = {}
    # Alias targets are known Tag instances in the database
    for target_name, _ in alias_map.values():
        existing_tags_by_name[target_name.lower()] = target_name

    CHUNK_SIZE = 500
    chk_list = list(all_canonical_names)
    for i in range(0, len(chk_list), CHUNK_SIZE):
        chunk = chk_list[i:i + CHUNK_SIZE]
        tags = db.query(Tag.name).filter(or_(Tag.name.in_(chunk), func.lower(Tag.name).in_(chunk))).all()
        for t in tags:
            existing_tags_by_name[t.name.lower()] = t.name

    # 3. Process each item
    results = {}
    for item in payload.items:
        item_key = str(item.id)

        # Canonicalize current tags preserving order
        resolved_current = []
        seen_current_lower = set()
        for t in item.current_tags:
            clean = t.strip().replace(" ", "_")
            if not clean:
                continue
            norm = clean.lower()
            raw_lower = t.strip().lower()

            canonical = None
            if norm in alias_map:
                target_name = alias_map[norm][0]
                canonical = existing_tags_by_name.get(target_name.lower(), target_name)
            elif raw_lower in alias_map:
                target_name = alias_map[raw_lower][0]
                canonical = existing_tags_by_name.get(target_name.lower(), target_name)
            elif norm in existing_tags_by_name:
                canonical = existing_tags_by_name[norm]
            elif raw_lower in existing_tags_by_name:
                canonical = existing_tags_by_name[raw_lower]
            else:
                canonical = clean

            canonical_norm = canonical.lower()
            if canonical_norm not in seen_current_lower:
                seen_current_lower.add(canonical_norm)
                resolved_current.append(canonical)

        # Canonicalize new tags preserving order, strictly verifying that the tag exists or resolves to an existing tag
        resolved_new = []
        seen_new_lower = set()
        for t in item.new_tags:
            clean = t.strip().replace(" ", "_")
            if not clean:
                continue
            norm = clean.lower()
            raw_lower = t.strip().lower()

            canonical = None
            if norm in alias_map:
                target_name = alias_map[norm][0]
                canonical = existing_tags_by_name.get(target_name.lower())
            elif raw_lower in alias_map:
                target_name = alias_map[raw_lower][0]
                canonical = existing_tags_by_name.get(target_name.lower())
            elif norm in existing_tags_by_name:
                canonical = existing_tags_by_name[norm]
            elif raw_lower in existing_tags_by_name:
                canonical = existing_tags_by_name[raw_lower]

            # If the tag does NOT exist in the database (as a tag or alias to an existing tag), SKIP IT
            if not canonical:
                continue

            canonical_norm = canonical.lower()
            if canonical_norm not in seen_current_lower and canonical_norm not in seen_new_lower:
                seen_new_lower.add(canonical_norm)
                resolved_new.append(canonical)

        # Combined tag list for implication expansion (only real tags!)
        combined_for_implications = resolved_current + resolved_new
        implied_names = resolve_implications(db, combined_for_implications)

        # Query database casing for any implied tags not yet in map
        missing_implied = [imp.lower() for imp in implied_names if imp.lower() not in existing_tags_by_name]
        if missing_implied:
            for t in db.query(Tag.name).filter(or_(Tag.name.in_(missing_implied), func.lower(Tag.name).in_(missing_implied))).all():
                existing_tags_by_name[t.name.lower()] = t.name

        # Process implied tags (must exist in database)
        resolved_implied = []
        seen_all_lower = set(seen_current_lower | seen_new_lower)
        for imp in implied_names:
            clean = imp.strip().replace(" ", "_")
            if not clean:
                continue
            norm = clean.lower()

            canonical = None
            if norm in alias_map:
                target_name = alias_map[norm][0]
                canonical = existing_tags_by_name.get(target_name.lower())
            elif norm in existing_tags_by_name:
                canonical = existing_tags_by_name[norm]

            if not canonical:
                continue

            canonical_norm = canonical.lower()
            if canonical_norm not in seen_all_lower:
                seen_all_lower.add(canonical_norm)
                resolved_implied.append(canonical)

        final_tags = resolved_current + resolved_new + resolved_implied

        # Determine newly added tags compared to original initial tags
        initial_lower_set = {t.strip().lower().replace(" ", "_") for t in item.current_tags if t.strip()}
        initial_lower_set.update({t.strip().lower() for t in item.current_tags if t.strip()})
        initial_lower_set.update(seen_current_lower)
        added_tags = [t for t in final_tags if t.lower() not in initial_lower_set]

        results[item_key] = {
            "current_tags": resolved_current,
            "new_tags": final_tags,
            "added_tags": added_tags
        }

    alias_resolutions = {k: v[0] for k, v in alias_map.items()}
    return {"results": results, "alias_resolutions": alias_resolutions}

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
        search_lower = search.strip().lower()
        priority = case(
            (func.lower(Tag.name) == search_lower, 1),
            (Tag.name.ilike(f"{search_lower}%"), 2),
            else_=3
        )
        query = query.filter(Tag.name.ilike(f"%{search_lower}%"))
        if category:
            query = query.filter(Tag.category == category)
        query = query.order_by(
            priority,
            desc(Tag.post_count),
            func.length(Tag.name),
            Tag.name
        )
    else:
        if category:
            query = query.filter(Tag.category == category)
        query = query.order_by(desc(Tag.post_count), func.length(Tag.name), Tag.name)
    
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
    
    q_lower = q.strip().lower()
    if not q_lower:
        return []
    
    priority = case(
        (func.lower(Tag.name) == q_lower, 1),
        (Tag.name.ilike(f"{q_lower}%"), 2),
        else_=3
    )
    
    tags = db.query(Tag).filter(
        Tag.name.ilike(f"%{q_lower}%")
    ).order_by(
        priority,
        desc(Tag.post_count),
        func.length(Tag.name),
        Tag.name
    ).limit(50).all()
    
    seen_tags = {tag.name for tag in tags}
    results = [
        {"name": tag.name, "category": tag.category, "count": tag.post_count}
        for tag in tags
    ]
    
    if len(results) < 50:
        aliases = (
            db.query(TagAlias)
            .filter(TagAlias.alias_name.ilike(f"{q_lower}%"))
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
    custom_filter: Optional[List[str]] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get tags most commonly co-occurring with the given search query results."""
    if not isinstance(limit, int) or limit <= 0:
        limit = 20
    if not isinstance(q, str) or not q.strip():
        return []

    parsed = parse_search_query(q)

    # Build media subquery using the full search pipeline
    media_query = db.query(Media.id)
    media_query = apply_search_criteria(media_query, parsed, db)

    # Apply top-level rating filter if not already specified in query string
    if rating and 'rating' not in parsed['meta']:
        ratings_list = [r.strip().lower() for r in rating.split(",") if r.strip()]
        valid_ratings = [RatingEnum[r] for r in ratings_list if r in RatingEnum.__members__]
        if valid_ratings:
            media_query = media_query.filter(Media.rating.in_(valid_ratings))

    if custom_filter:
        media_query = apply_custom_filters_or(media_query, custom_filter, db)

    media_subquery = media_query.subquery()

    # Non-negated, non-wildcard tag names to exclude
    excluded_tag_names = [name.lower() for name in parsed["tags"]["include"]]

    cooccurrence_query = (
        db.query(
            Tag,
            func.count(blombooru_media_tags.c.media_id).label("frequency"),
        )
        .join(blombooru_media_tags, blombooru_media_tags.c.tag_id == Tag.id)
        .filter(blombooru_media_tags.c.media_id.in_(media_subquery.select()))
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

@router.get("/suggested")
async def get_suggested_tags(
    tags: str = Query(default="", description="Comma-separated list of tag names"),
    limit: int = Query(default=20, ge=1, le=50),
    category: Optional[str] = Query(default=None),
):
    """
    Get suggested tags based on category-weighted TF-IDF similarity index.
    NOTE: Do not confuse with the autocomplete endpoint!
    """
    from ..services.similarity import similarity_index

    if similarity_index.rebuild_pending:
        await similarity_index.wait_for_build(timeout=10.0)

    if not similarity_index.is_ready:
        return {"items": [], "status": "building"}

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    if not tag_list:
        return {"items": [], "status": "ready"}

    results = similarity_index.get_suggested_tags(
        tag_names=tag_list,
        limit=limit,
        category_filter=category,
    )

    if results is None:
        return {"items": [], "status": "building"}

    return {"items": results, "status": "ready"}

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

    alias_existing = db.query(TagAlias).filter(TagAlias.alias_name == tag_data.name.lower()).first()
    if alias_existing:
        raise HTTPException(status_code=400, detail="Tag alias with this name already exists")
    
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
