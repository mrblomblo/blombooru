from typing import List, Optional, Set
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)
from sqlalchemy.orm import Session, selectinload
from ...config import settings
from ...database import get_db
from ...enums import RatingEnum, parse_rating_filter, rating_to_str
from ...models import Album, Media, blombooru_album_media
from ...schemas import (
    AlbumListResponse,
    MediaAlbumContextAlbum,
    MediaAlbumContextResponse,
    MediaResponse,
)
from ...utils.album_utils import get_bulk_album_thumbnails, get_bulk_parent_ids, get_flattened_media_ids
from ...utils.cache import cache_response
from ...utils.logger import logger
from ...utils.media_sort import apply_media_sort, get_media_sort_clauses
from ...utils.search_parser import apply_custom_filters_or, apply_search_criteria, parse_search_query

router = APIRouter()

@router.get("/{media_id}/related")
@cache_response(expire=600, key_prefix="related_media")
async def get_related_media(
    request: Request,
    media_id: int,
    limit: int = Query(12, ge=1, le=100),
    album_id: Optional[int] = Query(None),
    q: Optional[str] = Query(default=None),
    rating: Optional[str] = Query(default=None),
    custom_filter: Optional[List[str]] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Get related media items using category-weighted TF-IDF similarity."""
    from ...services.similarity import similarity_index

    if not isinstance(limit, int) or limit <= 0:
        limit = 12
    if not isinstance(q, str) or not q.strip():
        q = None
    else:
        q = q.strip()
    if not isinstance(rating, str) or not rating.strip():
        rating = None
    else:
        rating = rating.strip()
    clean_custom_filter = None
    if isinstance(custom_filter, (list, tuple, set)):
        clean_custom_filter = [cf.strip() for cf in custom_filter if isinstance(cf, str) and cf.strip()]
        if not clean_custom_filter:
            clean_custom_filter = None
    elif isinstance(custom_filter, str) and custom_filter.strip():
        clean_custom_filter = [custom_filter.strip()]

    if similarity_index.rebuild_pending:
        await similarity_index.wait_for_build(timeout=10.0)

    if not similarity_index.is_ready:
        return {"items": [], "status": "building"}

    album_media_ids = None
    if isinstance(album_id, int):
        album_media_ids = set(get_flattened_media_ids(db, album_id))
        if not album_media_ids:
            return {"items": [], "status": "ready"}

    # Exclude parent, siblings, and children of current media
    excluded_hierarchy_ids: Set[int] = set()
    curr_media = db.query(Media.parent_id).filter(Media.id == media_id).first()
    if curr_media:
        parent_id = curr_media[0]
        if parent_id is not None:
            # Parent
            excluded_hierarchy_ids.add(parent_id)
            # Siblings (and self)
            for (sid,) in db.query(Media.id).filter(Media.parent_id == parent_id).all():
                excluded_hierarchy_ids.add(sid)
        # Children
        for (cid,) in db.query(Media.id).filter(Media.parent_id == media_id).all():
            excluded_hierarchy_ids.add(cid)

    has_filters = bool(q or rating or clean_custom_filter)
    candidate_media_ids = None

    if has_filters:
        media_filter_query = db.query(Media.id).distinct().filter(Media.id != media_id)
        if album_media_ids is not None:
            media_filter_query = media_filter_query.filter(Media.id.in_(album_media_ids))

        parsed = parse_search_query(q or "")
        media_filter_query = apply_search_criteria(media_filter_query, parsed, db)

        if rating and 'rating' not in parsed.get('meta', {}):
            valid_ratings = parse_rating_filter(rating)
            if valid_ratings:
                media_filter_query = media_filter_query.filter(Media.rating.in_(valid_ratings))
            else:
                return {"items": [], "status": "ready"}

        if clean_custom_filter:
            media_filter_query = apply_custom_filters_or(media_filter_query, clean_custom_filter, db)

        media_filter_query = media_filter_query.order_by(None)
        matching_rows = media_filter_query.all()
        candidate_media_ids = {r[0] for r in matching_rows}
        if not candidate_media_ids:
            return {"items": [], "status": "ready"}

    similar_pairs = similarity_index.get_similar_media(
        media_id=media_id,
        limit=limit,
        album_media_ids=album_media_ids if not has_filters else None,
        candidate_media_ids=candidate_media_ids,
        excluded_media_ids=excluded_hierarchy_ids,
    )

    if not similar_pairs:
        return {"items": [], "status": "ready"}

    similar_ids = [mid for mid, _ in similar_pairs if mid not in excluded_hierarchy_ids]
    if not similar_ids:
        return {"items": [], "status": "ready"}

    media_records = db.query(Media).options(selectinload(Media.tags), selectinload(Media.media_tag_links)).filter(Media.id.in_(similar_ids)).all()
    media_dict = {m.id: m for m in media_records}

    items = []
    for mid in similar_ids:
        if mid in media_dict and mid not in excluded_hierarchy_ids:
            items.append(MediaResponse.model_validate(media_dict[mid]))
            if len(items) >= limit:
                break

    return {"items": items, "status": "ready"}

def _build_album_media_id_query(
    db: Session,
    album_id: int,
    q: Optional[str] = None,
    rating: Optional[str] = None,
    custom_filter: Optional[List[str]] = None,
    sort: Optional[str] = None,
    order: Optional[str] = None,
    seed: Optional[str] = None,
    fallback_sort: Optional[str] = None,
    fallback_order: Optional[str] = None,
):
    """Build the ordered query of Media.id within an album matching the given filters and sort."""
    media_query = db.query(Media.id).join(
        blombooru_album_media,
        Media.id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id == album_id
    )

    parsed = None
    if q:
        parsed = parse_search_query(q)
        if rating and 'rating' not in parsed['meta']:
            parsed['meta']['rating'] = [{'value': rating.lower(), 'negated': False}]
        media_query = apply_search_criteria(media_query, parsed, db)
    else:
        if rating:
            valid_ratings = parse_rating_filter(rating)
            if valid_ratings:
                media_query = media_query.filter(Media.rating.in_(valid_ratings))

    if custom_filter:
        media_query = apply_custom_filters_or(media_query, custom_filter, db)

    has_positive_similar_to = bool(
        q and parsed and any(
            not item['negated']
            for key in ('similar_to', 'similar_to_strict')
            for item in parsed['meta'].get(key, [])
        )
    )
    if (not q or not parsed or ('order' not in parsed['meta'] and 'sort' not in parsed['meta'])) and not (has_positive_similar_to and not sort):
        album_defaults = db.query(Album.default_sort, Album.default_order).filter(Album.id == album_id).first()
        sort_by = sort
        if not sort_by:
            if album_defaults and album_defaults.default_sort:
                sort_by = album_defaults.default_sort
            else:
                has_manual_media = db.query(blombooru_album_media.c.media_id).filter(
                    blombooru_album_media.c.album_id == album_id,
                    blombooru_album_media.c.sort_position.isnot(None)
                ).limit(1).scalar() is not None
                sort_by = "manual" if has_manual_media else settings.get_default_sort()

        if order:
            sort_order = order
        elif sort_by == "manual":
            sort_order = "asc"
        elif not sort and album_defaults and album_defaults.default_sort and album_defaults.default_order:
            sort_order = album_defaults.default_order
        else:
            sort_order = settings.get_default_order()
        media_query = media_query.order_by(None)
        if sort_by == "manual":
            fb_sort = fallback_sort if isinstance(fallback_sort, str) and fallback_sort.strip() else "uploaded_at"
            fb_order = fallback_order.lower() if isinstance(fallback_order, str) and fallback_order.lower() in ("asc", "desc") else "desc"
            fb_media_clauses = get_media_sort_clauses(
                fb_sort,
                fb_order,
                db,
                seed,
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
                sort_by,
                sort_order,
                db,
                seed,
                column_overrides={
                    'uploaded_at': Media.id,
                    'last_modified': Media.id,
                    'name': Media.filename,
                },
            )

    return media_query

@router.get("/{media_id}/adjacent")
async def get_adjacent_media(
    media_id: int,
    mode: Optional[str] = "search",
    album_id: Optional[int] = None,
    q: Optional[str] = None,
    rating: Optional[str] = None,
    custom_filter: Optional[List[str]] = Query(default=None),
    sort: Optional[str] = None,
    order: Optional[str] = None,
    seed: Optional[str] = None,
    fallback_sort: Optional[str] = None,
    fallback_order: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get previous and next media IDs relative to media_id within the given context."""
    try:
        if mode == "album" and album_id is not None:
            media_query = _build_album_media_id_query(
                db=db,
                album_id=album_id,
                q=q,
                rating=rating,
                custom_filter=custom_filter,
                sort=sort,
                order=order,
                seed=seed,
                fallback_sort=fallback_sort,
                fallback_order=fallback_order,
            )
        else:
            media_query = db.query(Media.id)

            parsed = parse_search_query(q or "")
            if rating and 'rating' not in parsed['meta']:
                parsed['meta']['rating'] = [{'value': rating.lower(), 'negated': False}]

            media_query = apply_search_criteria(media_query, parsed, db)
            if custom_filter:
                media_query = apply_custom_filters_or(media_query, custom_filter, db)

            has_positive_similar_to = bool(
                q and any(
                    not item['negated']
                    for key in ('similar_to', 'similar_to_strict')
                    for item in parsed['meta'].get(key, [])
                )
            )
            if 'order' not in parsed['meta'] and 'sort' not in parsed['meta'] and not (has_positive_similar_to and not sort):
                sort_by = sort if sort else settings.get_default_sort()
                sort_order = order if order else settings.get_default_order()
                media_query = media_query.order_by(None)
                media_query = apply_media_sort(media_query, sort_by, sort_order, db, seed)

        id_rows = media_query.all()
        id_list = [r[0] for r in id_rows]

        try:
            idx = id_list.index(media_id)
            prev_id = id_list[idx - 1] if idx > 0 else None
            next_id = id_list[idx + 1] if idx < len(id_list) - 1 else None
        except ValueError:
            prev_id = None
            next_id = None

        prev_hash = None
        prev_rating = None
        next_hash = None
        next_rating = None
        if prev_id:
            m_prev = db.query(Media.hash, Media.rating).filter(Media.id == prev_id).first()
            if m_prev:
                prev_hash = m_prev.hash
                prev_rating = rating_to_str(m_prev.rating)
        if next_id:
            m_next = db.query(Media.hash, Media.rating).filter(Media.id == next_id).first()
            if m_next:
                next_hash = m_next.hash
                next_rating = rating_to_str(m_next.rating)

        return {
            "prev_id": prev_id,
            "prev_hash": prev_hash,
            "prev_rating": prev_rating,
            "next_id": next_id,
            "next_hash": next_hash,
            "next_rating": next_rating
        }
    except Exception as e:
        logger.error(f"Error in get_adjacent_media: {e}")
        return {"prev_id": None, "prev_hash": None, "next_id": None, "next_hash": None}

@router.get("/{media_id}/album-context", response_model=MediaAlbumContextResponse)
async def get_media_album_context(
    media_id: int,
    album_id: int = Query(...),
    q: Optional[str] = Query(default=None),
    rating: Optional[str] = Query(default=None),
    custom_filter: Optional[List[str]] = Query(default=None),
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
    seed: Optional[str] = Query(default=None),
    fallback_sort: Optional[str] = Query(default=None),
    fallback_order: Optional[str] = Query(default=None),
    limit: int = Query(default=41, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get a windowed list of media items around media_id in an album's sort order."""
    media = db.query(Media.id).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    if not isinstance(limit, int) or limit <= 0:
        limit = 41
    limit = min(limit, 100)

    q_val = q if isinstance(q, str) and q.strip() else None
    rating_val = rating if isinstance(rating, str) and rating.strip() else None
    cf_val = list(custom_filter) if isinstance(custom_filter, (list, tuple, set)) else None
    sort_val = sort if isinstance(sort, str) and sort.strip() else None
    order_val = order if isinstance(order, str) and order.strip() else None
    seed_val = seed if isinstance(seed, str) and seed.strip() else None
    fb_sort_val = fallback_sort if isinstance(fallback_sort, str) and fallback_sort.strip() else None
    fb_order_val = fallback_order if isinstance(fallback_order, str) and fallback_order.strip() else None

    media_query = _build_album_media_id_query(
        db=db,
        album_id=album_id,
        q=q_val,
        rating=rating_val,
        custom_filter=cf_val,
        sort=sort_val,
        order=order_val,
        seed=seed_val,
        fallback_sort=fb_sort_val,
        fallback_order=fb_order_val,
    )

    id_list = [r[0] for r in media_query.all()]
    total = len(id_list)

    try:
        idx = id_list.index(media_id)
    except ValueError:
        return MediaAlbumContextResponse(
            album=MediaAlbumContextAlbum(id=album.id, name=album.name),
            position=None,
            total=total,
            start_index=0,
            has_prev_more=False,
            has_next_more=False,
            items=[]
        )

    if total <= limit:
        start = 0
        end = total
    else:
        half = limit // 2
        start = max(0, idx - half)
        end = start + limit
        if end > total:
            end = total
            start = max(0, end - limit)

    window_ids = id_list[start:end]
    records = db.query(Media).options(
        selectinload(Media.tags),
        selectinload(Media.media_tag_links)
    ).filter(Media.id.in_(window_ids)).all()
    media_map = {m.id: m for m in records}
    ordered_items = [MediaResponse.model_validate(media_map[mid]) for mid in window_ids if mid in media_map]

    return MediaAlbumContextResponse(
        album=MediaAlbumContextAlbum(id=album.id, name=album.name),
        position=idx + 1,
        total=total,
        start_index=start,
        has_prev_more=start > 0,
        has_next_more=end < total,
        items=ordered_items
    )

@router.get("/{media_id}/albums")
async def get_media_albums(
    media_id: int,
    db: Session = Depends(get_db)
):
    """Get all albums containing a specific media item"""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    albums = db.query(Album).join(
        blombooru_album_media,
        Album.id == blombooru_album_media.c.album_id
    ).filter(
        blombooru_album_media.c.media_id == media_id
    ).order_by(
        Album.name.asc(),
        Album.id.asc()
    ).all()
    
    if not albums:
        return {"albums": []}
    
    album_ids = [a.id for a in albums]
    thumbnails_map = get_bulk_album_thumbnails(album_ids, db, count=4)
    parent_crumbs = get_bulk_parent_ids(album_ids, db)

    all_parent_ids = set()
    for crumbs in parent_crumbs.values():
        all_parent_ids.update(crumbs)

    parent_names = {}
    if all_parent_ids:
        for pid, pname in db.query(Album.id, Album.name).filter(Album.id.in_(all_parent_ids)).all():
            parent_names[pid] = pname
    
    result = []
    for album in albums:
        thumb_info = thumbnails_map.get(album.id, {"paths": [], "ratings": []})
        crumbs = parent_crumbs.get(album.id, [])
        parent_path = " > ".join(parent_names[pid] for pid in crumbs if pid in parent_names) if crumbs else None
        result.append(
            AlbumListResponse(
                id=album.id,
                name=album.name,
                last_modified=album.last_modified,
                thumbnail_paths=thumb_info.get("paths", []),
                thumbnail_ratings=thumb_info.get("ratings", []),
                rating=album.cached_rating or RatingEnum.safe,
                media_count=album.cached_media_count or 0,
                parent_path=parent_path
            )
        )
    
    return {"albums": result}
