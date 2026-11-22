from typing import Dict, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
from ...auth import require_admin_mode
from ...config import settings
from ...database import get_db
from ...enums import RatingEnum, is_rating_filter_active, parse_rating_filter
from ...models import (
    Media,
    Tag,
    User,
    blombooru_media_tags,
)
from ...schemas import (
    BatchMediaRequest,
    BatchMetadataRequest,
    BulkMediaRatingUpdateRequest,
    BulkMediaRatingUpdateResponse,
    BulkTagUpdateRequest,
    BulkTagUpdateResponse,
    MediaResponse,
)
from ...utils.album_utils import handle_media_rating_changed
from ...utils.cache import (
    cache_response,
    invalidate_media_cache,
    invalidate_media_item_cache,
    invalidate_tag_cache,
)
from ...utils.logger import logger
from ...utils.media_helpers import extract_media_metadata
from ...utils.media_sort import apply_media_sort
from ...utils.request_helpers import safe_error_detail
from ...utils.search_parser import apply_custom_filters_or
from ...utils.tag_utils import convert_implied_by_names_to_ids, get_escalated_rating, validate_and_resolve_implied_by_ids
from .tags import _normalize_db_implied_by_ids, update_tag_counts

router = APIRouter()

# Maximum number of IDs per SQL IN-clause to avoid parameter limits
BATCH_CHUNK_SIZE = 500

@router.get("/")
@cache_response(expire=3600, key_prefix="media_list")
async def get_media_list(
    request: Request,
    page: int = 1,
    limit: int = Query(None),
    rating: Optional[str] = None,
    custom_filter: Optional[List[str]] = Query(default=None),
    sort: Optional[str] = None,
    order: Optional[str] = None,
    seed: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Get paginated media list"""
    if limit is None or not isinstance(limit, int):
        limit = settings.get_items_per_page()
    
    try:
        query = db.query(Media).options(selectinload(Media.tags), selectinload(Media.media_tag_links))
        
        rating_str = rating if isinstance(rating, str) else None
        valid_ratings = parse_rating_filter(rating_str) if rating_str else None
        sidebar_rating_active = is_rating_filter_active(valid_ratings) if valid_ratings else False
        if valid_ratings:
            query = query.filter(Media.rating.in_(valid_ratings))

        custom_filter_list = custom_filter if isinstance(custom_filter, (list, tuple, set)) else None
        custom_filter_active = bool(custom_filter_list and any(cf.strip() for cf in custom_filter_list if isinstance(cf, str)))
        if custom_filter_active:
            query = apply_custom_filters_or(query, custom_filter_list, db)
        
        # Sorting
        sort_by = sort if sort else settings.get_default_sort()
        sort_order = order if order else settings.get_default_order()
        query = apply_media_sort(query, sort_by, sort_order, db, seed)
        
        # Pagination
        offset = (page - 1) * limit
        
        from sqlalchemy import func
        query = query.add_columns(func.count(Media.id).over().label('total_count'))
        
        results = query.offset(offset).limit(limit).all()
        
        if results:
            total = results[0].total_count
            media_list = [r[0] for r in results]
        else:
            total = 0
            media_list = []
        
        items = [MediaResponse.model_validate(m) for m in media_list]
        
        if total == 0 and (sidebar_rating_active or custom_filter_active):
            unfiltered_total = db.query(func.count(Media.id)).scalar()
        else:
            unfiltered_total = total
        
        return {
            "items": items,
            "total": total,
            "unfiltered_total": unfiltered_total,
            "page": page,
            "pages": max(1, (total + limit - 1) // limit)
        }
    except Exception as e:
        logger.error(f"Error in get_media_list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to retrieve media list", e))

def _fetch_media_batch_tags_only(db: Session, media_ids: List[int], include_metadata: bool = False) -> List[dict]:
    """Fast projection query returning only id, filename, file_type, tags (name, category, rating), and optional metadata."""
    results = []
    
    for i in range(0, len(media_ids), BATCH_CHUNK_SIZE):
        chunk_ids = media_ids[i:i + BATCH_CHUNK_SIZE]
        query_cols = [
            Media.id,
            Media.filename,
            Media.file_type,
            Media.rating,
            Tag.id,
            Tag.name,
            Tag.category,
            Tag.rating,
            blombooru_media_tags.c.implied,
            blombooru_media_tags.c.implied_by,
        ]
        if include_metadata:
            query_cols.append(Media.path)

        query = (
            db.query(*query_cols)
            .filter(Media.id.in_(chunk_ids))
            .outerjoin(blombooru_media_tags, Media.id == blombooru_media_tags.c.media_id)
            .outerjoin(Tag, blombooru_media_tags.c.tag_id == Tag.id)
            .order_by(Media.id)
        )
        rows = query.all()

        chunk_id_to_name: dict[int, str] = {}
        missing_trigger_ids: set[int] = set()
        for row in rows:
            t_id = row[4]
            t_name = row[5]
            if t_id is not None and t_name:
                chunk_id_to_name[t_id] = t_name
        for row in rows:
            if row[8] and isinstance(row[9], list):
                for grp in row[9]:
                    if isinstance(grp, list):
                        for item in grp:
                            if isinstance(item, int) and not isinstance(item, bool):
                                if item not in chunk_id_to_name:
                                    missing_trigger_ids.add(item)
                            elif isinstance(item, str) and item.strip().isdigit():
                                tid_int = int(item.strip())
                                if tid_int not in chunk_id_to_name:
                                    missing_trigger_ids.add(tid_int)

        if missing_trigger_ids:
            for tid, tname in db.query(Tag.id, Tag.name).filter(Tag.id.in_(list(missing_trigger_ids))).all():
                chunk_id_to_name[tid] = tname

        media_map = {}
        for row in rows:
            m_id = row[0]
            filename = row[1]
            file_type = row[2]
            media_rating = row[3]
            tag_name = row[5]
            tag_cat = row[6]
            tag_rating = row[7]
            tag_implied = row[8]
            tag_implied_by = row[9]
            rel_path = row[10] if include_metadata else None

            if m_id not in media_map:
                ft_val = file_type.value if hasattr(file_type, 'value') else file_type
                r_val = media_rating.value if hasattr(media_rating, 'value') else (media_rating or "safe")
                item_dict = {
                    "id": m_id,
                    "filename": filename,
                    "file_type": ft_val,
                    "rating": r_val,
                    "tags": []
                }
                if include_metadata:
                    meta = None
                    if rel_path:
                        fpath = settings.BASE_DIR / rel_path
                        if fpath.exists():
                            try:
                                meta = extract_media_metadata(fpath)
                            except Exception:
                                pass
                    item_dict["metadata"] = meta
                media_map[m_id] = item_dict

            if tag_name:
                cat_val = tag_cat.value if hasattr(tag_cat, 'value') else tag_cat
                rat_val = tag_rating.value if hasattr(tag_rating, 'value') else (tag_rating or "none")
                is_imp = bool(tag_implied)
                resolved_imp_by: list[list[str]] = []
                if is_imp and isinstance(tag_implied_by, list):
                    for grp in tag_implied_by:
                        if not isinstance(grp, list):
                            continue
                        names_grp: list[str] = []
                        for item in grp:
                            name_val: Optional[str] = None
                            if isinstance(item, int) and not isinstance(item, bool):
                                name_val = chunk_id_to_name.get(item)
                            elif isinstance(item, str):
                                s = item.strip()
                                if s.isdigit():
                                    name_val = chunk_id_to_name.get(int(s))
                                elif s:
                                    name_val = s.lower()
                            if name_val and name_val not in names_grp:
                                names_grp.append(name_val)
                        if names_grp:
                            names_grp.sort()
                            if names_grp not in resolved_imp_by:
                                resolved_imp_by.append(names_grp)
                media_map[m_id]["tags"].append({
                    "name": tag_name,
                    "category": cat_val,
                    "rating": rat_val,
                    "implied": is_imp,
                    "implied_by": resolved_imp_by,
                })

        for m_id in chunk_ids:
            if m_id in media_map:
                results.append(media_map[m_id])
    return results

def _fetch_media_batch_full(db: Session, media_ids: List[int]) -> List[dict]:
    """Full MediaResponse batch serialization in chunks to respect parameter limits."""
    results = []
    for i in range(0, len(media_ids), BATCH_CHUNK_SIZE):
        chunk_ids = media_ids[i:i + BATCH_CHUNK_SIZE]
        media_list = db.query(Media).options(selectinload(Media.tags), selectinload(Media.media_tag_links)).filter(Media.id.in_(chunk_ids)).all()
        media_dict = {m.id: m for m in media_list}
        for m_id in chunk_ids:
            if m_id in media_dict:
                results.append(MediaResponse.model_validate(media_dict[m_id]))
    return results

@router.get("/batch")
async def get_media_batch(
    ids: str = Query(..., description="Comma-separated list of media IDs"),
    projection: Optional[str] = Query(None, description="Optional projection, e.g. 'tags_only' or 'ai_metadata'"),
    db: Session = Depends(get_db)
):
    """Get multiple media items by their IDs in a single request"""
    try:
        media_ids = [int(id_str.strip()) for id_str in ids.split(",") if id_str.strip().isdigit()]
        if not media_ids:
            return {"items": []}
            
        if projection == "tags_only":
            items = _fetch_media_batch_tags_only(db, media_ids, include_metadata=False)
        elif projection in ("ai_metadata", "tags_and_metadata"):
            items = _fetch_media_batch_tags_only(db, media_ids, include_metadata=True)
        else:
            items = _fetch_media_batch_full(db, media_ids)
            
        return {"items": items}
    except Exception as e:
        logger.error(f"Error in get_media_batch: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to retrieve media batch", e))

@router.post("/batch")
async def post_media_batch(
    payload: BatchMediaRequest,
    db: Session = Depends(get_db)
):
    """Get multiple media items by their IDs via POST body."""
    try:
        if not payload.ids:
            return {"items": []}
            
        if payload.projection == "tags_only":
            items = _fetch_media_batch_tags_only(db, payload.ids, include_metadata=False)
        elif payload.projection in ("ai_metadata", "tags_and_metadata"):
            items = _fetch_media_batch_tags_only(db, payload.ids, include_metadata=True)
        else:
            items = _fetch_media_batch_full(db, payload.ids)
            
        return {"items": items}
    except Exception as e:
        logger.error(f"Error in post_media_batch: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to retrieve media batch", e))

@router.post("/batch-metadata")
async def post_media_batch_metadata(
    payload: BatchMetadataRequest,
    db: Session = Depends(get_db)
):
    """Get metadata for multiple media items by their IDs."""
    try:
        if not payload.ids:
            return {"items": {}}

        results = {}
        for i in range(0, len(payload.ids), BATCH_CHUNK_SIZE):
            chunk = payload.ids[i:i + BATCH_CHUNK_SIZE]
            rows = db.query(Media.id, Media.path).filter(Media.id.in_(chunk)).all()
            for mid, rel_path in rows:
                if rel_path:
                    file_path = settings.BASE_DIR / rel_path
                    if file_path.exists():
                        try:
                            meta = extract_media_metadata(file_path)
                            if meta:
                                results[str(mid)] = meta
                        except Exception:
                            pass
        return {"items": results}
    except Exception as e:
        logger.error(f"Error in post_media_batch_metadata: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail("Failed to retrieve media metadata batch", e))

@router.post("/bulk-update-tags", response_model=BulkTagUpdateResponse)
async def bulk_update_tags(
    payload: BulkTagUpdateRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Atomically update tags across multiple media items with pre-validation and conflict-safe tag creation."""
    if not payload.items:
        return BulkTagUpdateResponse(status="success", updated_count=0, updated_media_ids=[])

    # 1. Pre-validation
    requested_ids = [item.id for item in payload.items]
    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(status_code=400, detail="Duplicate media IDs in update request")

    existing_media_ids = set()
    for i in range(0, len(requested_ids), BATCH_CHUNK_SIZE):
        chunk = requested_ids[i:i + BATCH_CHUNK_SIZE]
        found_ids = [r[0] for r in db.query(Media.id).filter(Media.id.in_(chunk)).all()]
        existing_media_ids.update(found_ids)

    missing_ids = set(requested_ids) - existing_media_ids
    if missing_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Media items not found: {sorted(list(missing_ids))[:10]}"
        )

    for item in payload.items:
        for tag in item.tags:
            if not isinstance(tag, str) or not tag.strip():
                raise HTTPException(status_code=400, detail=f"Invalid empty tag name for media ID {item.id}")
            if len(tag.strip()) > 255:
                raise HTTPException(status_code=400, detail=f"Tag name exceeds 255 characters: {tag[:30]}...")

    # 2. Collect unique tag names across entire batch and resolve aliases
    from ...utils.tag_utils import resolve_aliases, expand_implications
    from ...models import TagAlias

    all_raw_tags = set()
    for item in payload.items:
        for tag in item.tags:
            norm = tag.strip().lower()
            if norm:
                all_raw_tags.add(norm)
        if item.implied_tags:
            for k in item.implied_tags.keys():
                norm_k = k.strip().lower()
                if norm_k:
                    all_raw_tags.add(norm_k)

    alias_map = resolve_aliases(db, list(all_raw_tags))

    resolved_unique_names = set()
    for name in all_raw_tags:
        if name in alias_map:
            resolved_unique_names.add(alias_map[name][0].lower())
        else:
            resolved_unique_names.add(name)

    # 3. Concurrency-safe / upsert tag creation
    existing_tags_map = {}
    resolved_list = list(resolved_unique_names)
    for i in range(0, len(resolved_list), BATCH_CHUNK_SIZE):
        chunk = resolved_list[i:i + BATCH_CHUNK_SIZE]
        tags = db.query(Tag).filter(Tag.name.in_(chunk)).all()
        for t in tags:
            existing_tags_map[t.name.lower()] = t

    missing_tag_names = [n for n in resolved_unique_names if n not in existing_tags_map]

    if missing_tag_names:
        if db.bind and db.bind.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            stmt = sqlite_insert(Tag).values([
                {"name": name, "category": "general", "post_count": 0}
                for name in missing_tag_names
            ]).on_conflict_do_nothing(index_elements=["name"])
        else:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(Tag).values([
                {"name": name, "category": "general", "post_count": 0}
                for name in missing_tag_names
            ]).on_conflict_do_nothing(index_elements=["name"])
        db.execute(stmt)
        db.flush()

        # Re-query all resolved tags to ensure complete map
        for i in range(0, len(resolved_list), BATCH_CHUNK_SIZE):
            chunk = resolved_list[i:i + BATCH_CHUNK_SIZE]
            tags = db.query(Tag).filter(Tag.name.in_(chunk)).all()
            for t in tags:
                existing_tags_map[t.name.lower()] = t

    # 4. Fetch old tags to compute affected tag IDs and preserve implied metadata
    old_tag_ids = set()
    old_tag_ids_by_media: Dict[int, set] = {}
    old_tag_meta_by_media: Dict[int, Dict[int, tuple[bool, list[list[str]]]]] = {}
    for i in range(0, len(requested_ids), BATCH_CHUNK_SIZE):
        chunk = requested_ids[i:i + BATCH_CHUNK_SIZE]
        rows = db.query(
            blombooru_media_tags.c.media_id,
            blombooru_media_tags.c.tag_id,
            blombooru_media_tags.c.implied,
            blombooru_media_tags.c.implied_by,
        ).filter(blombooru_media_tags.c.media_id.in_(chunk)).all()
        for m_id, t_id, is_imp, imp_by in rows:
            old_tag_ids.add(t_id)
            old_tag_ids_by_media.setdefault(m_id, set()).add(t_id)
            old_tag_meta_by_media.setdefault(m_id, {})[t_id] = (
                bool(is_imp),
                imp_by if isinstance(imp_by, list) else [],
            )

    # 5. Delete existing media tags for requested_ids
    for i in range(0, len(requested_ids), BATCH_CHUNK_SIZE):
        chunk = requested_ids[i:i + BATCH_CHUNK_SIZE]
        db.execute(
            blombooru_media_tags.delete().where(blombooru_media_tags.c.media_id.in_(chunk))
        )

    # 6. Build new associations
    new_associations = []
    affected_tag_ids = set(old_tag_ids)
    rating_changed_media = []

    media_map = {}
    for i in range(0, len(requested_ids), BATCH_CHUNK_SIZE):
        chunk = requested_ids[i:i + BATCH_CHUNK_SIZE]
        medias = db.query(Media).filter(Media.id.in_(chunk)).all()
        for m in medias:
            media_map[m.id] = m

    for item in payload.items:
        old_meta = old_tag_meta_by_media.get(item.id, {})
        old_explicit_ids = {tid for tid, (is_imp, _) in old_meta.items() if not is_imp}
        old_implied_by_id = {
            tid: _normalize_db_implied_by_ids(db, imp_by)
            for tid, (is_imp, imp_by) in old_meta.items()
            if is_imp
        }

        item_tag_set = {}
        for raw_tag in item.tags:
            norm = raw_tag.strip().lower()
            if not norm:
                continue
            resolved_name = alias_map[norm][0].lower() if norm in alias_map else norm
            tag_obj = existing_tags_map.get(resolved_name)
            if tag_obj:
                item_tag_set[tag_obj.id] = tag_obj

        validated_client_implied = validate_and_resolve_implied_by_ids(
            db, item_tag_set, item.implied_tags
        )

        item_implied_by_id: dict[int, list[list[int]]] = {}
        newly_added_explicit_names: set[str] = set()

        for tid, tag_obj in item_tag_set.items():
            if tid in old_explicit_ids:
                continue
            elif tid in old_implied_by_id:
                merged = list(old_implied_by_id[tid])
                for grp in validated_client_implied.get(tid, []):
                    if grp not in merged:
                        merged.append(grp)
                item_implied_by_id[tid] = merged
            else:
                if tid in validated_client_implied:
                    item_implied_by_id[tid] = list(validated_client_implied[tid])
                else:
                    newly_added_explicit_names.add(tag_obj.name.lower())

        should_expand = (item.implied_tags is None) or bool(newly_added_explicit_names)
        if should_expand and item_tag_set:
            seed_names = None if item.implied_tags is None else newly_added_explicit_names
            backend_implied_by = expand_implications(db, item_tag_set, seed_trigger_names=seed_names)
            backend_id_groups = convert_implied_by_names_to_ids(db, backend_implied_by, item_tag_set)
            for tid, tag_obj in item_tag_set.items():
                if tid in old_explicit_ids or tag_obj.name.lower() in newly_added_explicit_names:
                    continue
                if tid in backend_id_groups:
                    merged = item_implied_by_id.setdefault(tid, [])
                    for grp in backend_id_groups[tid]:
                        if grp not in merged:
                            merged.append(grp)

        media = media_map.get(item.id)
        if media:
            previously_attached = old_tag_ids_by_media.get(item.id, set())
            added_tags = [t for tid, t in item_tag_set.items() if tid not in previously_attached]
            escalated = get_escalated_rating(media.rating, added_tags)
            if escalated and media.rating != escalated:
                media.rating = escalated
                rating_changed_media.append((media.id, media.rating.value if hasattr(media.rating, "value") else media.rating))

        for tid in item_tag_set.keys():
            affected_tag_ids.add(tid)
            is_imp = tid in item_implied_by_id
            imp_by = item_implied_by_id.get(tid) if is_imp else None
            new_associations.append({
                "media_id": item.id,
                "tag_id": tid,
                "implied": is_imp,
                "implied_by": imp_by,
            })

    if new_associations:
        db.execute(blombooru_media_tags.insert(), new_associations)

    for m in media_map.values():
        db.expire(m, ["media_tag_links", "tags"])

    db.commit()

    for m_id, new_r in rating_changed_media:
        handle_media_rating_changed(db, m_id, new_r)

    # 7. Aggregate update tag counts
    if affected_tag_ids:
        update_tag_counts(db, list(affected_tag_ids))
        db.commit()

    try:
        invalidate_tag_cache()
    except Exception:
        pass

    return BulkTagUpdateResponse(
        status="success",
        updated_count=len(requested_ids),
        updated_media_ids=requested_ids
    )

@router.post("/bulk-update-ratings", response_model=BulkMediaRatingUpdateResponse)
async def bulk_update_ratings(
    payload: BulkMediaRatingUpdateRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Atomically update ratings across multiple media items."""
    if not payload.items:
        return BulkMediaRatingUpdateResponse(status="success", updated_count=0, updated_media_ids=[])

    requested_ids = [item.id for item in payload.items]
    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(status_code=400, detail="Duplicate media IDs in update request")

    existing_media_map = {}
    for i in range(0, len(requested_ids), BATCH_CHUNK_SIZE):
        chunk = requested_ids[i:i + BATCH_CHUNK_SIZE]
        found = db.query(Media).filter(Media.id.in_(chunk)).all()
        for m in found:
            existing_media_map[m.id] = m

    missing_ids = set(requested_ids) - set(existing_media_map.keys())
    if missing_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Media items not found: {sorted(list(missing_ids))[:10]}"
        )

    updated_ids = []
    rating_changed_media = []
    for item in payload.items:
        media = existing_media_map[item.id]
        norm_rating = RatingEnum.normalize(item.rating)
        if norm_rating and media.rating != norm_rating:
            media.rating = norm_rating
            rating_changed_media.append((media.id, norm_rating.value if hasattr(norm_rating, "value") else norm_rating))
            updated_ids.append(media.id)

    db.commit()

    for m_id, new_r in rating_changed_media:
        handle_media_rating_changed(db, m_id, new_r)

    if updated_ids:
        invalidate_media_cache()
        for m_id in updated_ids:
            invalidate_media_item_cache(m_id)

    return BulkMediaRatingUpdateResponse(
        status="success",
        updated_count=len(updated_ids),
        updated_media_ids=updated_ids
    )
