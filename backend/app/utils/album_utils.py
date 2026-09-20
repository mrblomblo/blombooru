from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from .cache import invalidate_album_cache
from ..models import (Album, Media, RatingEnum, blombooru_album_hierarchy,
                      blombooru_album_media, blombooru_media_tags, Tag)

RATING_PRIORITY = {RatingEnum.explicit: 3, RatingEnum.questionable: 2, RatingEnum.safe: 1}
PRIORITY_TO_RATING = {3: RatingEnum.explicit, 2: RatingEnum.questionable, 1: RatingEnum.safe}

def get_descendant_ids(db: Session, album_ids: List[int], max_depth: int = 100) -> Dict[int, Set[int]]:
    """Compute all descendant album IDs for all given IDs."""
    if not album_ids:
        return {}

    # Fetch all hierarchy links for fast graph traversal
    links = db.query(
        blombooru_album_hierarchy.c.parent_album_id,
        blombooru_album_hierarchy.c.child_album_id
    ).all()

    children_map: Dict[int, List[int]] = {}
    for pid, cid in links:
        children_map.setdefault(pid, []).append(cid)

    result: Dict[int, Set[int]] = {}
    for aid in album_ids:
        visited: Set[int] = {aid}
        queue: deque = deque([(aid, 0)])

        while queue:
            curr, depth = queue.popleft()
            if depth >= max_depth:
                break
            for child in children_map.get(curr, []):
                if child not in visited:
                    visited.add(child)
                    queue.append((child, depth + 1))

        result[aid] = visited

    return result

def get_parent_ids(album_id: int, db: Session, max_depth: int = 100) -> List[int]:
    """Get all parent album IDs in order from root down to immediate parent."""
    parent_ids = []
    current_id = album_id
    visited = set()

    while current_id and current_id not in visited and len(visited) < max_depth:
        visited.add(current_id)
        parent = db.query(blombooru_album_hierarchy.c.parent_album_id).filter(
            blombooru_album_hierarchy.c.child_album_id == current_id
        ).first()

        if parent and parent[0] not in visited:
            parent_ids.insert(0, parent[0])
            current_id = parent[0]
        else:
            break

    return parent_ids

def get_bulk_parent_ids(album_ids: List[int], db: Session, max_depth: int = 100) -> Dict[int, List[int]]:
    """Batch-resolve ancestor breadcrumbs for multiple album IDs."""
    if not album_ids:
        return {}

    links = db.query(
        blombooru_album_hierarchy.c.child_album_id,
        blombooru_album_hierarchy.c.parent_album_id
    ).all()

    parent_map: Dict[int, int] = {cid: pid for cid, pid in links}

    result: Dict[int, List[int]] = {}
    for aid in album_ids:
        crumbs = []
        curr = aid
        visited = set()
        while curr in parent_map and curr not in visited and len(visited) < max_depth:
            visited.add(curr)
            parent = parent_map[curr]
            if parent in visited:
                break
            crumbs.insert(0, parent)
            curr = parent
        result[aid] = crumbs

    return result

def get_all_ancestor_ids(db: Session, album_ids: List[int], max_depth: int = 100) -> Set[int]:
    """Find all ancestor album IDs for a given list of album IDs."""
    if not album_ids:
        return set()

    links = db.query(
        blombooru_album_hierarchy.c.child_album_id,
        blombooru_album_hierarchy.c.parent_album_id
    ).all()

    parent_map: Dict[int, int] = {cid: pid for cid, pid in links}

    all_ancestors: Set[int] = set()
    for aid in album_ids:
        curr = aid
        visited = set()
        while curr in parent_map and curr not in visited and len(visited) < max_depth:
            visited.add(curr)
            parent = parent_map[curr]
            if parent in visited:
                break
            all_ancestors.add(parent)
            curr = parent

    return all_ancestors

def recalculate_album_metrics(db: Session, album_ids: List[int]) -> None:
    """
    Recalculates cached_direct_media_count, cached_media_count, and cached_rating
    for the specified album_ids and all of their ancestors up the hierarchy.
    """
    if not album_ids:
        return

    # 1. Identify all affected albums (targets + all their ancestors)
    ancestors = get_all_ancestor_ids(db, album_ids)
    target_album_ids = set(album_ids) | ancestors
    if not target_album_ids:
        return

    # 2. Get all descendants of these target albums so sub-metrics can be folded upwards
    descendants_map = get_descendant_ids(db, list(target_album_ids))
    all_needed_album_ids: Set[int] = set()
    for desc_set in descendants_map.values():
        all_needed_album_ids.update(desc_set)

    if not all_needed_album_ids:
        return

    # 3. Query direct stats for all needed albums
    direct_stats = db.query(
        blombooru_album_media.c.album_id,
        Media.rating,
        func.count(Media.id).label('count')
    ).join(
        Media, Media.id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id.in_(all_needed_album_ids)
    ).group_by(
        blombooru_album_media.c.album_id, Media.rating
    ).all()

    direct_data: Dict[int, Dict[str, Any]] = {}
    for aid, rating, count in direct_stats:
        if aid not in direct_data:
            direct_data[aid] = {'count': 0, 'ratings': set()}
        direct_data[aid]['count'] += count
        if rating:
            direct_data[aid]['ratings'].add(rating)

    # 4. Fetch hierarchy edges for folding
    links = db.query(
        blombooru_album_hierarchy.c.parent_album_id,
        blombooru_album_hierarchy.c.child_album_id
    ).all()

    children_map: Dict[int, List[int]] = {}
    for pid, cid in links:
        children_map.setdefault(pid, []).append(cid)

    # 5. Compute recursive stats with memoization
    memo: Dict[int, Dict[str, Any]] = {}

    def compute(aid: int, visited: Set[int]) -> Dict[str, Any]:
        if aid in memo:
            return memo[aid]
        if aid in visited:
            return {'rating': RatingEnum.safe, 'count': 0, 'direct_count': 0}

        new_visited = visited | {aid}
        direct = direct_data.get(aid, {'count': 0, 'ratings': set()})
        direct_count = direct['count']
        current_ratings = set(direct['ratings'])
        total_count = direct_count

        for cid in children_map.get(aid, []):
            child_stats = compute(cid, new_visited)
            current_ratings.add(child_stats['rating'])
            total_count += child_stats['count']

        highest_rating = RatingEnum.safe
        if current_ratings:
            highest_rating = max(current_ratings, key=lambda r: RATING_PRIORITY.get(r, 0))

        res = {
            'rating': highest_rating,
            'count': total_count,
            'direct_count': direct_count
        }
        memo[aid] = res
        return res

    for aid in target_album_ids:
        compute(aid, set())

    # 6. Bulk update target albums
    for aid in target_album_ids:
        stats = memo.get(aid, {'rating': RatingEnum.safe, 'count': 0, 'direct_count': 0})
        db.query(Album).filter(Album.id == aid).update({
            Album.cached_rating: stats['rating'],
            Album.cached_media_count: stats['count'],
            Album.cached_direct_media_count: stats['direct_count'],
        }, synchronize_session=False)

    db.flush()

def recalculate_all_album_metrics(db: Session) -> None:
    """Recalculate metrics for all albums."""
    all_album_ids = [r[0] for r in db.query(Album.id).all()]
    if not all_album_ids:
        return

    # Direct stats for all albums
    direct_stats = db.query(
        blombooru_album_media.c.album_id,
        Media.rating,
        func.count(Media.id).label('count')
    ).join(
        Media, Media.id == blombooru_album_media.c.media_id
    ).group_by(
        blombooru_album_media.c.album_id, Media.rating
    ).all()

    direct_data: Dict[int, Dict[str, Any]] = {}
    for aid, rating, count in direct_stats:
        if aid not in direct_data:
            direct_data[aid] = {'count': 0, 'ratings': set()}
        direct_data[aid]['count'] += count
        if rating:
            direct_data[aid]['ratings'].add(rating)

    links = db.query(
        blombooru_album_hierarchy.c.parent_album_id,
        blombooru_album_hierarchy.c.child_album_id
    ).all()

    children_map: Dict[int, List[int]] = {}
    for pid, cid in links:
        children_map.setdefault(pid, []).append(cid)

    memo: Dict[int, Dict[str, Any]] = {}

    def compute(aid: int, visited: Set[int]) -> Dict[str, Any]:
        if aid in memo:
            return memo[aid]
        if aid in visited:
            return {'rating': RatingEnum.safe, 'count': 0, 'direct_count': 0}

        new_visited = visited | {aid}
        direct = direct_data.get(aid, {'count': 0, 'ratings': set()})
        direct_count = direct['count']
        current_ratings = set(direct['ratings'])
        total_count = direct_count

        for cid in children_map.get(aid, []):
            child_stats = compute(cid, new_visited)
            current_ratings.add(child_stats['rating'])
            total_count += child_stats['count']

        highest_rating = RatingEnum.safe
        if current_ratings:
            highest_rating = max(current_ratings, key=lambda r: RATING_PRIORITY.get(r, 0))

        res = {
            'rating': highest_rating,
            'count': total_count,
            'direct_count': direct_count
        }
        memo[aid] = res
        return res

    for aid in all_album_ids:
        compute(aid, set())

    for aid in all_album_ids:
        stats = memo.get(aid, {'rating': RatingEnum.safe, 'count': 0, 'direct_count': 0})
        db.query(Album).filter(Album.id == aid).update({
            Album.cached_rating: stats['rating'],
            Album.cached_media_count: stats['count'],
            Album.cached_direct_media_count: stats['direct_count'],
        }, synchronize_session=False)

    db.commit()

def update_album_last_modified(album_id_or_ids: Union[int, List[int]], db: Session):
    """Update last_modified timestamp for one or more albums."""
    if isinstance(album_id_or_ids, int):
        ids = [album_id_or_ids]
    else:
        ids = list(album_id_or_ids)
    if not ids:
        return

    db.query(Album).filter(Album.id.in_(ids)).update(
        {Album.last_modified: datetime.now()},
        synchronize_session=False
    )
    db.flush()

def set_media_albums(db: Session, media_id: int, album_ids: Optional[List[int]]) -> None:
    """Sets album memberships for a single media item."""
    target_album_ids = set(album_ids or [])

    # Fetch existing album memberships
    existing_album_ids = {
        r[0] for r in db.query(blombooru_album_media.c.album_id).filter(
            blombooru_album_media.c.media_id == media_id
        ).all()
    }

    if existing_album_ids == target_album_ids:
        return

    to_add = target_album_ids - existing_album_ids
    to_remove = existing_album_ids - target_album_ids

    if to_remove:
        db.execute(
            blombooru_album_media.delete().where(
                and_(
                    blombooru_album_media.c.media_id == media_id,
                    blombooru_album_media.c.album_id.in_(to_remove)
                )
            )
        )

    if to_add:
        # Validate that target album IDs exist
        valid_album_ids = {
            r[0] for r in db.query(Album.id).filter(Album.id.in_(to_add)).all()
        }
        if valid_album_ids:
            db.execute(
                blombooru_album_media.insert(),
                [{"album_id": aid, "media_id": media_id} for aid in valid_album_ids]
            )

    affected = existing_album_ids | target_album_ids
    if affected:
        update_album_last_modified(list(affected), db)
        recalculate_album_metrics(db, list(affected))
        db.commit()
        invalidate_album_cache()

def add_media_to_album(db: Session, album_id: int, media_ids: List[int]) -> int:
    """Album-centric bulk add with duplicate-membership prevention."""
    if not media_ids:
        return 0

    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    # Verify which media IDs exist
    valid_ids = {row[0] for row in db.query(Media.id).filter(Media.id.in_(media_ids)).all()}
    if not valid_ids:
        return 0

    # Find existing memberships
    existing_ids = {
        row[0] for row in db.query(blombooru_album_media.c.media_id).filter(
            and_(
                blombooru_album_media.c.album_id == album_id,
                blombooru_album_media.c.media_id.in_(valid_ids)
            )
        ).all()
    }

    new_ids = valid_ids - existing_ids
    if new_ids:
        db.execute(
            blombooru_album_media.insert(),
            [{"album_id": album_id, "media_id": mid} for mid in new_ids]
        )
        update_album_last_modified(album_id, db)
        recalculate_album_metrics(db, [album_id])
        db.commit()
        invalidate_album_cache()

    return len(new_ids)

def remove_media_from_album(db: Session, album_id: int, media_ids: List[int]) -> int:
    """Album-centric bulk remove."""
    if not media_ids:
        return 0

    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    result = db.execute(
        blombooru_album_media.delete().where(
            and_(
                blombooru_album_media.c.album_id == album_id,
                blombooru_album_media.c.media_id.in_(media_ids)
            )
        )
    )

    update_album_last_modified(album_id, db)
    recalculate_album_metrics(db, [album_id])
    db.commit()
    invalidate_album_cache()

    return result.rowcount or len(media_ids)

def handle_media_rating_changed(db: Session, media_id: int, new_rating: Optional[str]) -> None:
    """Triggered when a media item's rating changes."""
    album_ids = [
        r[0] for r in db.query(blombooru_album_media.c.album_id).filter(
            blombooru_album_media.c.media_id == media_id
        ).all()
    ]
    if album_ids:
        recalculate_album_metrics(db, album_ids)
        db.commit()
        invalidate_album_cache()

def handle_media_deleted(db: Session, media_ids: List[int]) -> None:
    """Captures album IDs before media deletion, and triggers metric recalculation afterwards."""
    if not media_ids:
        return

    affected_album_ids = [
        r[0] for r in db.query(blombooru_album_media.c.album_id).filter(
            blombooru_album_media.c.media_id.in_(media_ids)
        ).distinct().all()
    ]

    if affected_album_ids:
        db.execute(
            blombooru_album_media.delete().where(
                blombooru_album_media.c.media_id.in_(media_ids)
            )
        )
        recalculate_album_metrics(db, affected_album_ids)
        update_album_last_modified(affected_album_ids, db)
        db.commit()
        invalidate_album_cache()

def reparent_album(db: Session, album_id: int, new_parent_id: Optional[int]) -> None:
    """Changes an album's parent with deep cycle protection and ancestor metric recalculation."""
    if new_parent_id == album_id:
        raise HTTPException(status_code=400, detail="Album cannot be its own parent")

    if new_parent_id is not None:
        parent = db.query(Album).filter(Album.id == new_parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent album not found")

        # Deep cycle check: verify new_parent_id is not in album_id's descendants
        descendant_map = get_descendant_ids(db, [album_id])
        descendants = descendant_map.get(album_id, set())
        if new_parent_id in descendants:
            raise HTTPException(
                status_code=400,
                detail="Circular reference detected: cannot make an album a child of its own descendant"
            )

    # Capture old ancestors
    old_parents = set(get_parent_ids(album_id, db))

    # Remove old parent relationship
    db.execute(
        blombooru_album_hierarchy.delete().where(
            blombooru_album_hierarchy.c.child_album_id == album_id
        )
    )

    # Add new parent relationship
    if new_parent_id is not None:
        db.execute(
            blombooru_album_hierarchy.insert().values(
                parent_album_id=new_parent_id,
                child_album_id=album_id
            )
        )

    # Recalculate metrics on old ancestors, new ancestors, and target album
    new_parents = set(get_parent_ids(album_id, db)) if new_parent_id else set()
    affected = old_parents | new_parents | {album_id}
    recalculate_album_metrics(db, list(affected))
    db.commit()
    invalidate_album_cache()

def delete_album_cascade(db: Session, album_id: int, cascade: bool = False) -> None:
    """Deletes an album (optionally cascading to child albums) and updates ancestor metrics."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    # Capture ancestor breadcrumb trail before deletion
    parent_ids = get_parent_ids(album_id, db)

    if cascade:
        # Collect all descendant album IDs to delete
        descendant_map = get_descendant_ids(db, [album_id])
        descendants_to_delete = descendant_map.get(album_id, {album_id})

        # Delete all descendant albums
        db.query(Album).filter(Album.id.in_(descendants_to_delete)).delete(synchronize_session=False)
    else:
        # Just orphan direct children
        db.execute(
            blombooru_album_hierarchy.delete().where(
                blombooru_album_hierarchy.c.parent_album_id == album_id
            )
        )
        db.delete(album)

    db.commit()

    if parent_ids:
        recalculate_album_metrics(db, parent_ids)
        db.commit()

    invalidate_album_cache()

def get_bulk_album_thumbnails(album_ids: List[int], db: Session, count: int = 4) -> Dict[int, List[str]]:
    """Fetches up to `count` thumbnails for multiple albums using window functions."""
    if not album_ids:
        return {}

    # 1. Get all descendant album IDs for all requested albums
    descendant_map = get_descendant_ids(db, list(album_ids))
    all_needed_album_ids: Set[int] = set()
    for dset in descendant_map.values():
        all_needed_album_ids.update(dset)

    if not all_needed_album_ids:
        return {aid: [] for aid in album_ids}

    # 2. Windowed query to sample up to `count` thumbnails per sub-album
    rn_col = func.row_number().over(
        partition_by=blombooru_album_media.c.album_id,
        order_by=func.random()
    ).label("rn")

    subq = db.query(
        blombooru_album_media.c.album_id,
        Media.id.label("media_id"),
        rn_col
    ).join(
        Media, Media.id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id.in_(list(all_needed_album_ids)),
        or_(Media.thumbnail_path.isnot(None), Media.path.isnot(None))
    ).subquery()

    thumbnail_rows = db.query(
        subq.c.album_id,
        subq.c.media_id
    ).filter(subq.c.rn <= count).all()

    # Map sub-album to its thumbnails
    sub_thumbnails: Dict[int, List[int]] = {}
    for aid, mid in thumbnail_rows:
        sub_thumbnails.setdefault(aid, []).append(mid)

    # 3. For each requested album, prioritize direct media, then fold in descendant media
    thumbnails_map: Dict[int, List[str]] = {}
    for target_aid in album_ids:
        descendants = descendant_map.get(target_aid, {target_aid})
        gathered_mids: List[int] = []
        seen_mids: Set[int] = set()

        # Prioritize direct album media first
        for mid in sub_thumbnails.get(target_aid, []):
            if mid not in seen_mids:
                seen_mids.add(mid)
                gathered_mids.append(mid)

        # If we need more thumbnails, pull from descendant albums
        if len(gathered_mids) < count:
            for desc_aid in descendants:
                if desc_aid == target_aid:
                    continue
                for mid in sub_thumbnails.get(desc_aid, []):
                    if mid not in seen_mids:
                        seen_mids.add(mid)
                        gathered_mids.append(mid)
                        if len(gathered_mids) >= count:
                            break
                if len(gathered_mids) >= count:
                    break

        thumbnails_map[target_aid] = [f"/api/media/{mid}/thumbnail" for mid in gathered_mids[:count]]

    return thumbnails_map

def get_bulk_album_metrics(album_ids: List[int], db: Session) -> Dict[int, dict]:
    """Directly returns cached metrics for requested albums from indexed Album columns."""
    if not album_ids:
        return {}

    albums = db.query(
        Album.id,
        Album.cached_rating,
        Album.cached_media_count,
        Album.cached_direct_media_count
    ).filter(Album.id.in_(album_ids)).all()

    return {
        aid: {
            'rating': rating or RatingEnum.safe,
            'count': count or 0,
            'direct_count': direct_count or 0
        }
        for aid, rating, count, direct_count in albums
    }

def get_album_popular_tags(album_id: int, db: Session, limit: int = 20) -> List[dict]:
    """Aggregate and count top tags from media in an album and its descendants."""
    descendant_map = get_descendant_ids(db, [album_id])
    all_album_ids = list(descendant_map.get(album_id, {album_id}))

    tag_counts = db.query(
        Tag.id,
        Tag.name,
        Tag.category,
        func.count(blombooru_media_tags.c.tag_id).label('count')
    ).join(
        blombooru_media_tags, Tag.id == blombooru_media_tags.c.tag_id
    ).join(
        blombooru_album_media, blombooru_media_tags.c.media_id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id.in_(all_album_ids)
    ).group_by(
        Tag.id
    ).order_by(
        text('count DESC')
    ).limit(limit).all()

    return [
        {
            "id": tc.id,
            "name": tc.name,
            "category": tc.category.value if hasattr(tc.category, 'value') else tc.category,
            "count": tc.count
        }
        for tc in tag_counts
    ]

def get_flattened_media_ids(db: Session, root_album_id: int) -> List[int]:
    """Fetches all distinct media IDs for an album and all of its descendants."""
    descendant_map = get_descendant_ids(db, [root_album_id])
    all_album_ids = list(descendant_map.get(root_album_id, {root_album_id}))

    results = db.query(blombooru_album_media.c.media_id).filter(
        blombooru_album_media.c.album_id.in_(all_album_ids)
    ).distinct().all()

    return sorted(r[0] for r in results)

def get_album_tree_data(db: Session) -> List[dict]:
    """Returns complete album hierarchy nodes."""
    albums = db.query(
        Album.id,
        Album.name,
        Album.cached_rating,
        Album.cached_media_count,
        Album.cached_direct_media_count
    ).order_by(Album.name.asc()).all()

    if not albums:
        return []

    links = db.query(
        blombooru_album_hierarchy.c.parent_album_id,
        blombooru_album_hierarchy.c.child_album_id
    ).all()

    parent_map: Dict[int, int] = {cid: pid for pid, cid in links}
    children_count_map: Dict[int, int] = {}
    for pid, cid in links:
        children_map_pid = children_count_map.get(pid, 0)
        children_count_map[pid] = children_map_pid + 1

    # Compute depths
    depth_map: Dict[int, int] = {}
    for aid, name, rating, count, direct_count in albums:
        depth = 0
        curr = aid
        visited = set()
        while curr in parent_map and curr not in visited:
            visited.add(curr)
            depth += 1
            curr = parent_map[curr]
        depth_map[aid] = depth

    return [
        {
            "id": aid,
            "name": name,
            "parent_id": parent_map.get(aid),
            "depth": depth_map.get(aid, 0),
            "media_count": count or 0,
            "direct_media_count": direct_count or 0,
            "children_count": children_count_map.get(aid, 0),
            "rating": rating or RatingEnum.safe
        }
        for aid, name, rating, count, direct_count in albums
    ]


def get_album_stats(db: Session) -> dict:
    """Returns total album count, root album count, and total media in albums."""
    total_albums = db.query(func.count(Album.id)).scalar() or 0

    root_albums = db.query(func.count(Album.id)).filter(
        ~Album.id.in_(db.query(blombooru_album_hierarchy.c.child_album_id))
    ).scalar() or 0

    total_media_in_albums = db.query(func.count(func.distinct(blombooru_album_media.c.media_id))).scalar() or 0

    return {
        "total_albums": total_albums,
        "root_albums": root_albums,
        "total_media_in_albums": total_media_in_albums
    }
