from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session, selectinload

from ..auth import User, require_admin_mode
from ..config import settings
from ..database import get_db
from ..models import (Album, Media, RatingEnum, blombooru_album_hierarchy,
                      blombooru_album_media)
from ..schemas import (AlbumCreate, AlbumHierarchyResponse, AlbumListResponse, 
                        AlbumResponse, AlbumStatsResponse,
                        AlbumUpdate, MediaIds)
from ..utils.album_utils import (add_media_to_album, delete_album_cascade,
                                 get_album_popular_tags, get_album_stats,
                                 get_album_tree_data, get_bulk_album_thumbnails,
                                 get_bulk_parent_ids, get_parent_ids,
                                 recalculate_album_metrics, recalculate_all_album_metrics,
                                 remove_media_from_album, reparent_album)
from ..utils.cache import cache_response, invalidate_album_cache
from ..utils.media_sort import apply_album_sort, apply_media_sort
from ..utils.search_parser import (apply_custom_filters_or,
                                   apply_search_criteria, parse_search_query)

router = APIRouter(prefix="/api/albums", tags=["albums"])

def get_effective_limit(limit: Optional[int]) -> int:
    """Get effective limit, falling back to settings if not provided or invalid."""
    if limit is None or not isinstance(limit, int) or limit <= 0:
        return settings.get_items_per_page()
    return limit

@router.get("/", response_model=dict)
@router.get("", response_model=dict)
@cache_response(expire=3600, key_prefix="album_list")
async def get_albums(
    request: Request,
    page: int = 1,
    limit: Optional[int] = Query(default=None),
    sort: Optional[str] = Query(default="created_at"),
    order: Optional[str] = Query(default="desc"),
    seed: Optional[str] = Query(default=None),
    rating: Optional[str] = None,
    root_only: bool = Query(default=False),
    db: Session = Depends(get_db)
):
    """Get paginated album list using database-level sorting, filtering, and windowed thumbnails."""
    limit = get_effective_limit(limit)
    if not isinstance(page, int) or page <= 0:
        page = 1
    
    # Build query
    query = db.query(Album)
    
    if isinstance(root_only, bool) and root_only:
        # Only show albums that are not children of any other album
        query = query.filter(~Album.id.in_(db.query(blombooru_album_hierarchy.c.child_album_id)))
    
    if isinstance(rating, str) and rating.strip():
        ratings_list = [r.strip().lower() for r in rating.split(",") if r.strip()]
        valid_ratings = [RatingEnum[r] for r in ratings_list if r in RatingEnum.__members__]
        if valid_ratings:
            query = query.filter(Album.cached_rating.in_(valid_ratings))
    
    sort_str = sort if isinstance(sort, str) and sort else "created_at"
    sort_order = order.lower() if isinstance(order, str) and order.lower() in ("asc", "desc") else "desc"
    seed_str = seed if isinstance(seed, str) else None
    query = apply_album_sort(query, sort_str, sort_order, seed_str)
    
    total = query.count()
    offset = (page - 1) * limit
    page_albums = query.offset(offset).limit(limit).all()
    
    page_album_ids = [a.id for a in page_albums]
    thumbnails_map = get_bulk_album_thumbnails(page_album_ids, db, count=4)
    
    album_list = [
        AlbumListResponse(
            id=album.id,
            name=album.name,
            last_modified=album.last_modified,
            thumbnail_paths=thumbnails_map.get(album.id, []),
            rating=album.cached_rating or RatingEnum.safe,
            media_count=album.cached_media_count or 0
        )
        for album in page_albums
    ]
    
    return {
        "items": album_list,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit)
    }

@router.get("/tree", response_model=AlbumHierarchyResponse)
@cache_response(expire=3600, key_prefix="album_tree")
async def get_albums_tree(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get full album hierarchy in a single fast query for tree views, pickers, and selects."""
    tree_nodes = get_album_tree_data(db)
    return {"items": tree_nodes}

@router.get("/stats", response_model=AlbumStatsResponse)
async def get_album_statistics(
    db: Session = Depends(get_db)
):
    """Get aggregate album statistics (total, root, media) in fast queries."""
    return get_album_stats(db)

@router.post("/recalculate")
async def recalculate_all_albums_endpoint(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Recalculate all album cached metrics and purge cache."""
    recalculate_all_album_metrics(db)
    invalidate_album_cache()
    return {"message": "All album metrics successfully recalculated and cache invalidated"}

@router.get("/autocomplete")
@cache_response(expire=3600, key_prefix="album_autocomplete")
async def autocomplete_albums(
    request: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    if not isinstance(limit, int) or limit <= 0:
        limit = 50

    q_clean = q.strip().lower() if isinstance(q, str) else ""
    if not q_clean:
        return []

    priority = case(
        (func.lower(Album.name) == q_clean, 1),
        (Album.name.ilike(f"{q_clean}%"), 2),
        else_=3
    )

    albums = db.query(Album).filter(
        Album.name.ilike(f"%{q_clean}%")
    ).order_by(
        priority,
        desc(Album.cached_media_count),
        func.length(Album.name),
        Album.name
    ).limit(limit).all()

    album_ids = [a.id for a in albums]
    parent_crumbs = get_bulk_parent_ids(album_ids, db)

    all_parent_ids = set()
    for crumbs in parent_crumbs.values():
        all_parent_ids.update(crumbs)

    parent_names = {}
    if all_parent_ids:
        for pid, pname in db.query(Album.id, Album.name).filter(Album.id.in_(all_parent_ids)).all():
            parent_names[pid] = pname

    results = []
    for a in albums:
        crumbs = parent_crumbs.get(a.id, [])
        path_str = " > ".join(parent_names[pid] for pid in crumbs if pid in parent_names) if crumbs else None
        results.append({
            "id": a.id,
            "name": a.name,
            "parent_path": path_str,
            "media_count": a.cached_media_count or 0,
            "rating": a.cached_rating or RatingEnum.safe
        })

    return results

@router.get("/{album_id}", response_model=AlbumResponse)
async def get_album(
    album_id: int,
    db: Session = Depends(get_db)
):
    """Get single album details"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    children_count = db.query(func.count(blombooru_album_hierarchy.c.child_album_id)).filter(
        blombooru_album_hierarchy.c.parent_album_id == album_id
    ).scalar() or 0
    parent_ids = get_parent_ids(album.id, db)
    
    return AlbumResponse(
        id=album.id,
        name=album.name,
        created_at=album.created_at,
        updated_at=album.updated_at,
        last_modified=album.last_modified,
        media_count=album.cached_media_count or 0,
        children_count=children_count,
        rating=album.cached_rating or RatingEnum.safe,
        parent_ids=parent_ids
    )

@router.post("", response_model=AlbumResponse)
async def create_album(
    album_data: AlbumCreate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Create new album (admin only)"""
    # Check if parent exists
    if album_data.parent_album_id:
        parent = db.query(Album).filter(Album.id == album_data.parent_album_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent album not found")
    
    new_album = Album(
        name=album_data.name,
        cached_rating=RatingEnum.safe,
        cached_media_count=0,
        cached_direct_media_count=0
    )
    db.add(new_album)
    db.flush()
    
    # Set parent relationship if specified
    if album_data.parent_album_id:
        db.execute(
            blombooru_album_hierarchy.insert().values(
                parent_album_id=album_data.parent_album_id,
                child_album_id=new_album.id
            )
        )
        recalculate_album_metrics(db, [album_data.parent_album_id])
    
    db.commit()
    db.refresh(new_album)
    
    # Invalidate cache
    invalidate_album_cache()
    
    return AlbumResponse(
        id=new_album.id,
        name=new_album.name,
        created_at=new_album.created_at,
        updated_at=new_album.updated_at,
        last_modified=new_album.last_modified,
        media_count=0,
        children_count=0,
        rating=RatingEnum.safe,
        parent_ids=get_parent_ids(new_album.id, db)
    )

@router.put("/{album_id}", response_model=AlbumResponse)
async def update_album(
    album_id: int,
    album_data: AlbumUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Update album name/parent with deep cycle safety (admin only)"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    # Update name
    if album_data.name is not None:
        album.name = album_data.name
        db.flush()
    
    # Update parent relationship
    if album_data.parent_album_id is not None:
        reparent_album(db, album_id, album_data.parent_album_id or None)
    else:
        db.commit()
        invalidate_album_cache()
    
    db.refresh(album)
    return await get_album(album_id, db)

@router.delete("/{album_id}")
async def delete_album(
    album_id: int,
    cascade: bool = Query(default=False),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Delete album (admin only), updating ancestor metrics."""
    delete_album_cascade(db, album_id, cascade=cascade)
    return {"message": "Album deleted successfully"}

@router.post("/{album_id}/media")
async def add_media_to_album_endpoint(
    album_id: int,
    data: MediaIds,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Add media items to album (bulk operation with duplicate check, admin only)"""
    new_count = add_media_to_album(db, album_id, data.media_ids)
    return {"message": f"Added {new_count} media item(s) to album"}

@router.delete("/{album_id}/media")
async def remove_media_from_album_endpoint(
    album_id: int,
    data: MediaIds,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Remove media items from album (bulk operation, admin only)"""
    remove_media_from_album(db, album_id, data.media_ids)
    return {"message": "Media removed from album"}

@router.get("/{album_id}/contents")
@cache_response(expire=3600, key_prefix="album_contents")
async def get_album_contents(
    request: Request,
    album_id: int,
    page: int = Query(default=1, ge=1),
    limit: Optional[int] = Query(default=None),
    rating: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    custom_filter: Optional[List[str]] = Query(default=None),
    sort: str = Query(default="uploaded_at"),
    order: str = Query(default="desc"),
    seed: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Get album contents (media + sub-albums, paginated)"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    # Get effective limit from settings if not provided
    limit = get_effective_limit(limit)
    
    if not isinstance(page, int) or page <= 0:
        page = 1
    if not isinstance(sort, str):
        sort = "uploaded_at"
    if not isinstance(order, str):
        order = "desc"
    
    sort_order = order.lower() if order and order.lower() in ("asc", "desc") else "desc"
    
    # --- 1. MEDIA ITEMS ---
    from ..schemas import MediaResponse
    
    # Start query
    media_query = db.query(Media).join(
        blombooru_album_media,
        Media.id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id == album_id
    ).options(selectinload(Media.tags))
    
    # Apply tag filtering if query provided
    if q and isinstance(q, str):
        parsed = parse_search_query(q)
        
        # Merge rating filter into parsed query if provided and not already in query
        if rating and 'rating' not in parsed['meta']:
            parsed['meta']['rating'] = [{'value': rating.lower(), 'negated': False}]
        
        # Apply search criteria to media query
        media_query = apply_search_criteria(media_query, parsed, db)
    else:
        # Filter Rating (only if no tag query provided)
        if rating:
            ratings_list = [r.strip().lower() for r in rating.split(",") if r.strip()]
            valid_ratings = [RatingEnum[r] for r in ratings_list if r in RatingEnum.__members__]
            if valid_ratings:
                media_query = media_query.filter(Media.rating.in_(valid_ratings))
    
    if custom_filter:
        media_query = apply_custom_filters_or(media_query, custom_filter, db)
    
    # Sort Media
    if not q or not isinstance(q, str) or ('order' not in parsed['meta'] and 'sort' not in parsed['meta']):
        media_query = media_query.order_by(None)
        media_query = apply_media_sort(
            media_query,
            sort,
            sort_order,
            db,
            seed,
            column_overrides={
                'uploaded_at': Media.id,
                'last_modified': Media.id,
                'name': Media.filename,
            },
        )

    # Get total count BEFORE pagination
    total_media = media_query.count()
    
    # Calculate offset and apply pagination
    offset = (page - 1) * limit
    media_items = media_query.offset(offset).limit(limit).all()
    
    # --- 2. SUB-ALBUMS ---
    child_albums_query = db.query(Album).join(
        blombooru_album_hierarchy,
        Album.id == blombooru_album_hierarchy.c.child_album_id
    ).filter(
        blombooru_album_hierarchy.c.parent_album_id == album_id
    )
    
    if rating:
        ratings_list = [r.strip().lower() for r in rating.split(",") if r.strip()]
        valid_ratings = [RatingEnum[r] for r in ratings_list if r in RatingEnum.__members__]
        if valid_ratings:
            child_albums_query = child_albums_query.filter(Album.cached_rating.in_(valid_ratings))
    
    child_albums_query = apply_album_sort(child_albums_query, sort, sort_order, seed)
    child_albums = child_albums_query.all()
    
    child_ids = [c.id for c in child_albums]
    child_thumbnails_map = get_bulk_album_thumbnails(child_ids, db, count=4)
    
    child_album_list = [
        AlbumListResponse(
            id=child.id,
            name=child.name,
            last_modified=child.last_modified,
            thumbnail_paths=child_thumbnails_map.get(child.id, []),
            rating=child.cached_rating or RatingEnum.safe,
            media_count=child.cached_media_count or 0
        )
        for child in child_albums
    ]
    
    total_pages = max(1, (total_media + limit - 1) // limit)
    
    return {
        "media": [MediaResponse.model_validate(m) for m in media_items],
        "albums": child_album_list,
        "total_media": total_media,
        "page": page,
        "limit": limit,
        "pages": total_pages
    }

@router.get("/{album_id}/tags")
async def get_album_tags_endpoint(
    album_id: int,
    limit: int = Query(default=20),
    db: Session = Depends(get_db)
):
    """Get popular tags within an album and its children in 1 query."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    tags = get_album_popular_tags(album_id, db, limit=limit)
    return {"tags": tags}

@router.get("/{album_id}/children", response_model=List[AlbumListResponse])
async def get_child_albums(
    album_id: int,
    db: Session = Depends(get_db)
):
    """Get direct child albums with windowed thumbnails"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    children = db.query(Album).join(
        blombooru_album_hierarchy,
        Album.id == blombooru_album_hierarchy.c.child_album_id
    ).filter(
        blombooru_album_hierarchy.c.parent_album_id == album_id
    ).order_by(Album.name.asc()).all()
    
    if not children:
        return []
    
    child_ids = [c.id for c in children]
    thumbnails_map = get_bulk_album_thumbnails(child_ids, db, count=4)
    
    return [
        AlbumListResponse(
            id=child.id,
            name=child.name,
            last_modified=child.last_modified,
            thumbnail_paths=thumbnails_map.get(child.id, []),
            rating=child.cached_rating or RatingEnum.safe,
            media_count=child.cached_media_count or 0
        )
        for child in children
    ]

@router.get("/{album_id}/parents")
async def get_parent_albums(
    album_id: int,
    db: Session = Depends(get_db)
):
    """Get parent album chain (breadcrumb) in 1 query"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    parent_ids = get_parent_ids(album_id, db)
    if not parent_ids:
        return {"parents": []}
    
    parent_map = {a.id: a.name for a in db.query(Album.id, Album.name).filter(Album.id.in_(parent_ids)).all()}
    parents = [
        {"id": pid, "name": parent_map[pid]}
        for pid in parent_ids if pid in parent_map
    ]
    
    return {"parents": parents}
