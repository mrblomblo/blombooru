from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, desc, func, literal, or_
from sqlalchemy.orm import Session, selectinload

from ..auth import User, require_admin_mode
from ..config import settings
from ..database import get_db
from ..enums import is_rating_filter_active, parse_rating_filter
from ..models import (Album, Media, RatingEnum, blombooru_album_hierarchy,
                      blombooru_album_media)
from ..schemas import (AlbumCreate, AlbumHierarchyResponse, AlbumListResponse, 
                        AlbumResponse, AlbumStatsResponse,
                        AlbumUpdate, MediaIds,
                        AlbumReorderRequest, MediaReorderRequest)
from ..utils.album_utils import (add_media_to_album, apply_media_filters,
                                 delete_album_cascade,
                                 get_album_matching_media_counts,
                                 get_album_popular_tags, get_album_stats,
                                 get_album_tree_data, get_bulk_album_thumbnails,
                                 get_bulk_parent_ids, get_matching_album_ids,
                                 get_parent_ids, is_album_filter_active,
                                 recalculate_album_metrics, recalculate_all_album_metrics,
                                 prune_all_albums, remove_media_from_album, reparent_album)
from ..utils.cache import cache_response, invalidate_album_cache
from ..utils.media_sort import (apply_album_sort, apply_media_sort,
                                get_album_sort_clauses, get_media_sort_clauses)
from ..utils.search_parser import parse_search_query

router = APIRouter(prefix="/api/albums", tags=["albums"])

def get_effective_limit(limit: Optional[int]) -> int:
    """Get effective limit, falling back to settings if not provided or invalid."""
    if limit is None or not isinstance(limit, int) or limit <= 0:
        return settings.get_items_per_page()
    return limit


@router.get("/", response_model=dict)
@router.get("", response_model=dict)
async def get_albums(
    request: Request,
    page: int = 1,
    limit: Optional[int] = Query(default=None),
    sort: Optional[str] = Query(default="created_at"),
    order: Optional[str] = Query(default="desc"),
    fallback_sort: Optional[str] = Query(default=None),
    fallback_order: Optional[str] = Query(default=None),
    seed: Optional[str] = Query(default=None),
    rating: Optional[str] = None,
    custom_filter: Optional[List[str]] = Query(default=None),
    q: Optional[str] = Query(default=None),
    root_only: bool = Query(default=False),
    db: Session = Depends(get_db)
):
    """Get paginated album list using database-level sorting, filtering, and windowed thumbnails."""
    # Build query
    query = db.query(Album)
    
    if isinstance(root_only, bool) and root_only:
        # Only show albums that are not children of any other album
        query = query.filter(~Album.id.in_(db.query(blombooru_album_hierarchy.c.child_album_id)))
    
    filter_active = is_album_filter_active(rating=rating, custom_filter=custom_filter, q=q)
    if filter_active:
        matching_ids = get_matching_album_ids(db, rating=rating, custom_filter=custom_filter, q=q)
        if not matching_ids:
            query = query.filter(literal(False))
        else:
            query = query.filter(Album.id.in_(matching_ids))
    
    sort_str = sort if isinstance(sort, str) and sort else "created_at"
    sort_order = order.lower() if isinstance(order, str) and order.lower() in ("asc", "desc") else "desc"
    seed_str = seed if isinstance(seed, str) else None

    # Manual sort only applies to root albums (where sort_position is defined)
    if sort_str == "manual" and root_only:
        fb_sort = fallback_sort if isinstance(fallback_sort, str) and fallback_sort.strip() else "created_at"
        fb_order = fallback_order.lower() if isinstance(fallback_order, str) and fallback_order.lower() in ("asc", "desc") else "desc"
        fb_clauses = get_album_sort_clauses(fb_sort, fb_order, seed_str)
        query = query.order_by(Album.sort_position.asc().nulls_last(), *fb_clauses)
    else:
        query = apply_album_sort(query, sort_str, sort_order, seed_str)
    
    total = query.count()
    limit = get_effective_limit(limit)
    if not isinstance(page, int) or page <= 0:
        page = 1
    offset = (page - 1) * limit
    page_albums = query.offset(offset).limit(limit).all()
    pages = max(1, (total + limit - 1) // limit)
    
    page_album_ids = [a.id for a in page_albums]
    thumbnails_map = get_bulk_album_thumbnails(
        page_album_ids, db, count=4, rating=rating, custom_filter=custom_filter, q=q
    )
    if filter_active:
        counts_map = get_album_matching_media_counts(
            page_album_ids, db, rating=rating, custom_filter=custom_filter, q=q
        )
    else:
        counts_map = {a.id: (a.cached_media_count or 0) for a in page_albums}
    
    album_list = []
    for album in page_albums:
        thumb_info = thumbnails_map.get(album.id, {"paths": [], "ratings": []})
        album_list.append(
            AlbumListResponse(
                id=album.id,
                name=album.name,
                last_modified=album.last_modified,
                thumbnail_paths=thumb_info.get("paths", []),
                thumbnail_ratings=thumb_info.get("ratings", []),
                rating=album.cached_rating or RatingEnum.safe,
                media_count=counts_map[album.id]
            )
        )
    
    rating_str = rating if isinstance(rating, str) else None
    valid_ratings = parse_rating_filter(rating_str) if rating_str else None
    sidebar_rating_active = is_rating_filter_active(valid_ratings) if valid_ratings else False
    custom_filter_list = custom_filter if isinstance(custom_filter, (list, tuple, set)) else None
    custom_filter_active = bool(custom_filter_list and any(cf.strip() for cf in custom_filter_list if isinstance(cf, str)))
    sidebar_filters_active = sidebar_rating_active or custom_filter_active

    visible_count = len([a for a in album_list if (a.media_count > 0 or getattr(a, 'children_count', 0) > 0)])
    if visible_count == 0 and sidebar_filters_active:
        unfiltered_q = db.query(Album)
        if isinstance(root_only, bool) and root_only:
            unfiltered_q = unfiltered_q.filter(~Album.id.in_(db.query(blombooru_album_hierarchy.c.child_album_id)))
        q_str = q if isinstance(q, str) and q.strip() else None
        if q_str:
            matching_q = get_matching_album_ids(db, q=q_str)
            if not matching_q:
                unfiltered_total = 0
            else:
                unfiltered_total = unfiltered_q.filter(Album.id.in_(matching_q)).count()
        else:
            unfiltered_total = unfiltered_q.filter(
                or_(
                    Album.cached_media_count > 0,
                    Album.id.in_(db.query(blombooru_album_hierarchy.c.parent_album_id))
                )
            ).count()
    else:
        unfiltered_total = total

    return {
        "items": album_list,
        "total": total,
        "unfiltered_total": unfiltered_total,
        "page": page,
        "limit": limit,
        "pages": pages
    }

@router.put("/reorder")
async def reorder_root_albums(
    data: AlbumReorderRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Set manual sort positions for root albums."""
    for position, album_id in enumerate(data.album_ids):
        db.query(Album).filter(Album.id == album_id).update(
            {Album.sort_position: position},
            synchronize_session=False
        )
    db.commit()
    invalidate_album_cache()
    return {"message": "Root album order updated"}

@router.delete("/reorder")
async def clear_root_albums_order(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Clear manual sort positions for root albums."""
    db.query(Album).update({Album.sort_position: None}, synchronize_session=False)
    db.commit()
    invalidate_album_cache()
    return {"message": "Root album manual order cleared"}

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

@router.post("/prune")
async def prune_all_albums_endpoint(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Prune all albums that contains no media and that have no children."""
    pruned = prune_all_albums(db)
    invalidate_album_cache()
    return {"message": "Albums have been pruned successfully", "count": pruned}

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
    fields_set = album_data.model_fields_set if hasattr(album_data, "model_fields_set") else getattr(album_data, "__fields_set__", set())
    if "parent_album_id" in fields_set:
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
    fallback_sort: Optional[str] = Query(default=None),
    fallback_order: Optional[str] = Query(default=None),
    seed: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Get album contents (media + sub-albums, paginated)"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    if not isinstance(page, int) or page <= 0:
        page = 1
    if not isinstance(sort, str):
        sort = "uploaded_at"
    if not isinstance(order, str):
        order = "desc"
    
    sort_order = order.lower() if order and order.lower() in ("asc", "desc") else "desc"
    fb_sort = fallback_sort if isinstance(fallback_sort, str) and fallback_sort.strip() else "uploaded_at"
    fb_order = fallback_order.lower() if isinstance(fallback_order, str) and fallback_order.lower() in ("asc", "desc") else "desc"
    seed_str = seed if isinstance(seed, str) else None
    
    # --- 1. MEDIA ITEMS ---
    from ..schemas import MediaResponse
    
    # Start query
    media_query = db.query(Media).join(
        blombooru_album_media,
        Media.id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id == album_id
    ).options(selectinload(Media.tags), selectinload(Media.media_tag_links))
    
    parsed_q = parse_search_query(q) if (q and isinstance(q, str) and q.strip()) else None
    media_query = apply_media_filters(
        media_query, db, rating=rating, custom_filter=custom_filter, q=q, parsed_q=parsed_q, apply_sort=True
    )
    
    # Sort Media
    has_q_sort = bool(parsed_q and ('order' in parsed_q.get('meta', {}) or 'sort' in parsed_q.get('meta', {})))
    if not has_q_sort:
        media_query = media_query.order_by(None)
        if sort == "manual":
            fb_media_clauses = get_media_sort_clauses(
                fb_sort,
                fb_order,
                db,
                seed_str,
                column_overrides={
                    'uploaded_at': Media.id,
                    'last_modified': Media.id,
                    'name': Media.filename,
                },
            )
            media_query = media_query.order_by(
                blombooru_album_media.c.sort_position.asc().nulls_last(),
                *fb_media_clauses
            )
        else:
            media_query = apply_media_sort(
                media_query,
                sort,
                sort_order,
                db,
                seed_str,
                column_overrides={
                    'uploaded_at': Media.id,
                    'last_modified': Media.id,
                    'name': Media.filename,
                },
            )

    # Get total count BEFORE pagination
    total_media = media_query.count()
    limit = get_effective_limit(limit)
    offset = (page - 1) * limit
    media_items = media_query.offset(offset).limit(limit).all()
    total_pages = max(1, (total_media + limit - 1) // limit)
    
    # --- 2. SUB-ALBUMS ---
    child_albums_query = db.query(Album).join(
        blombooru_album_hierarchy,
        Album.id == blombooru_album_hierarchy.c.child_album_id
    ).filter(
        blombooru_album_hierarchy.c.parent_album_id == album_id
    )
    
    child_filter_active = is_album_filter_active(rating=rating, custom_filter=custom_filter, q=q)
    if child_filter_active:
        matching_child_ids = get_matching_album_ids(db, rating=rating, custom_filter=custom_filter, q=q)
        if not matching_child_ids:
            child_albums_query = child_albums_query.filter(literal(False))
        else:
            child_albums_query = child_albums_query.filter(Album.id.in_(matching_child_ids))
    
    if sort == "manual":
        fb_subalbum_clauses = get_album_sort_clauses(
            fb_sort,
            fb_order,
            seed_str
        )
        child_albums_query = child_albums_query.order_by(
            blombooru_album_hierarchy.c.sort_position.asc().nulls_last(),
            *fb_subalbum_clauses
        )
    else:
        child_albums_query = apply_album_sort(child_albums_query, sort, sort_order, seed_str)

    child_albums = child_albums_query.all()
    
    child_ids = [c.id for c in child_albums]
    child_thumbnails_map = get_bulk_album_thumbnails(
        child_ids, db, count=4, rating=rating, custom_filter=custom_filter, q=q
    )
    if child_filter_active:
        child_counts_map = get_album_matching_media_counts(
            child_ids, db, rating=rating, custom_filter=custom_filter, q=q
        )
    else:
        child_counts_map = {c.id: (c.cached_media_count or 0) for c in child_albums}
    
    child_album_list = []
    for child in child_albums:
        thumb_info = child_thumbnails_map.get(child.id, {"paths": [], "ratings": []})
        child_album_list.append(
            AlbumListResponse(
                id=child.id,
                name=child.name,
                last_modified=child.last_modified,
                thumbnail_paths=thumb_info.get("paths", []),
                thumbnail_ratings=thumb_info.get("ratings", []),
                rating=child.cached_rating or RatingEnum.safe,
                media_count=child_counts_map[child.id]
            )
        )
    
    rating_str = rating if isinstance(rating, str) else None
    valid_ratings = parse_rating_filter(rating_str) if rating_str else None
    sidebar_rating_active = is_rating_filter_active(valid_ratings) if valid_ratings else False
    custom_filter_list = custom_filter if isinstance(custom_filter, (list, tuple, set)) else None
    custom_filter_active = bool(custom_filter_list and any(cf.strip() for cf in custom_filter_list if isinstance(cf, str)))
    sidebar_filters_active = sidebar_rating_active or custom_filter_active

    if sidebar_filters_active:
        unfiltered_media_q = db.query(func.count(Media.id)).join(
            blombooru_album_media,
            Media.id == blombooru_album_media.c.media_id
        ).filter(
            blombooru_album_media.c.album_id == album_id
        )
        q_str = q if isinstance(q, str) and q.strip() else None
        if q_str:
            unfiltered_media_q = apply_media_filters(unfiltered_media_q, db, q=q_str)
        unfiltered_total_media = unfiltered_media_q.scalar()

        unfiltered_child_q = db.query(Album).join(
            blombooru_album_hierarchy,
            Album.id == blombooru_album_hierarchy.c.child_album_id
        ).filter(
            blombooru_album_hierarchy.c.parent_album_id == album_id
        )
        if q_str:
            matching_child_q = get_matching_album_ids(db, q=q_str)
            if not matching_child_q:
                unfiltered_child_q = unfiltered_child_q.filter(literal(False))
            else:
                unfiltered_child_q = unfiltered_child_q.filter(Album.id.in_(matching_child_q))
        unfiltered_total_albums = unfiltered_child_q.filter(
            or_(
                Album.cached_media_count > 0,
                Album.id.in_(db.query(blombooru_album_hierarchy.c.parent_album_id))
            )
        ).count()
    else:
        unfiltered_total_media = total_media
        unfiltered_total_albums = len([c for c in child_album_list if (c.media_count > 0 or getattr(c, 'children_count', 0) > 0)])
    
    return {
        "media": [MediaResponse.model_validate(m) for m in media_items],
        "albums": child_album_list,
        "total_media": total_media,
        "unfiltered_total_media": unfiltered_total_media,
        "unfiltered_total_albums": unfiltered_total_albums,
        "page": page,
        "limit": limit,
        "pages": total_pages
    }

@router.put("/{album_id}/media/reorder")
async def reorder_album_media(
    album_id: int,
    data: MediaReorderRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Set manual sort positions for media within an album."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    for position, media_id in enumerate(data.media_ids):
        db.execute(
            blombooru_album_media.update()
            .where(
                blombooru_album_media.c.album_id == album_id,
                blombooru_album_media.c.media_id == media_id
            )
            .values(sort_position=position)
        )
    db.commit()
    invalidate_album_cache()
    return {"message": "Album media order updated"}

@router.delete("/{album_id}/media/reorder")
async def clear_album_media_order(
    album_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Clear manual media order for an album."""
    db.execute(
        blombooru_album_media.update()
        .where(blombooru_album_media.c.album_id == album_id)
        .values(sort_position=None)
    )
    db.commit()
    invalidate_album_cache()
    return {"message": "Manual media order cleared"}

@router.put("/{album_id}/sub-albums/reorder")
async def reorder_sub_albums(
    album_id: int,
    data: AlbumReorderRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Set manual sort positions for child albums under this parent."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    for position, child_id in enumerate(data.album_ids):
        db.execute(
            blombooru_album_hierarchy.update()
            .where(
                blombooru_album_hierarchy.c.parent_album_id == album_id,
                blombooru_album_hierarchy.c.child_album_id == child_id
            )
            .values(sort_position=position)
        )
    db.commit()
    invalidate_album_cache()
    return {"message": "Sub-album order updated"}

@router.delete("/{album_id}/sub-albums/reorder")
async def clear_sub_albums_order(
    album_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Clear manual sub-album order for an album."""
    db.execute(
        blombooru_album_hierarchy.update()
        .where(blombooru_album_hierarchy.c.parent_album_id == album_id)
        .values(sort_position=None)
    )
    db.commit()
    invalidate_album_cache()
    return {"message": "Manual sub-album order cleared"}

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
    
    result = []
    for child in children:
        thumb_info = thumbnails_map.get(child.id, {"paths": [], "ratings": []})
        result.append(
            AlbumListResponse(
                id=child.id,
                name=child.name,
                last_modified=child.last_modified,
                thumbnail_paths=thumb_info.get("paths", []),
                thumbnail_ratings=thumb_info.get("ratings", []),
                rating=child.cached_rating or RatingEnum.safe,
                media_count=child.cached_media_count or 0
            )
        )
    return result

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
