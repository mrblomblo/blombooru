from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import List
import random
from datetime import datetime

from ..models import Album, Media, RatingEnum, blombooru_album_media, blombooru_album_hierarchy

def get_album_rating(album_id: int, db: Session, visited: set = None) -> RatingEnum:
    """Recursively compute the highest rating of all media in album and its children"""
    if visited is None:
        visited = set()
    
    if album_id in visited:
        return RatingEnum.safe
    
    visited.add(album_id)
    
    # Get ratings from direct media in this album
    media_ratings = db.query(Media.rating).join(
        blombooru_album_media,
        Media.id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id == album_id
    ).all()
    
    # Get ratings from child albums (recursive)
    child_album_ids = db.query(blombooru_album_hierarchy.c.child_album_id).filter(
        blombooru_album_hierarchy.c.parent_album_id == album_id
    ).all()
    
    all_ratings = [r[0] for r in media_ratings]
    
    for child_id_tuple in child_album_ids:
        child_rating = get_album_rating(child_id_tuple[0], db, visited)
        all_ratings.append(child_rating)
    
    if not all_ratings:
        return RatingEnum.safe
    
    # Return highest rating (explicit > questionable > safe)
    rating_priority = {RatingEnum.explicit: 3, RatingEnum.questionable: 2, RatingEnum.safe: 1}
    return max(all_ratings, key=lambda r: rating_priority[r])

def get_album_tags(album_id: int, db: Session, visited: set = None) -> List[dict]:
    """Recursively aggregate all tags from media in album and its children"""
    if visited is None:
        visited = set()
    
    if album_id in visited:
        return []
    
    visited.add(album_id)
    
    # Get tags from direct media in this album
    from ..models import Tag
    media_tags = db.query(Tag).join(
        Media.tags
    ).join(
        blombooru_album_media,
        Media.id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id == album_id
    ).distinct().all()
    
    # Get tags from child albums (recursive)
    child_album_ids = db.query(blombooru_album_hierarchy.c.child_album_id).filter(
        blombooru_album_hierarchy.c.parent_album_id == album_id
    ).all()
    
    all_tags = {tag.id: tag for tag in media_tags}
    
    for child_id_tuple in child_album_ids:
        child_tags = get_album_tags(child_id_tuple[0], db, visited)
        for tag_dict in child_tags:
            all_tags[tag_dict['id']] = tag_dict
    
    return [{'id': tag.id if hasattr(tag, 'id') else tag['id'], 
             'name': tag.name if hasattr(tag, 'name') else tag['name']} 
            for tag in all_tags.values()]

def get_random_thumbnails(album_id: int, db: Session, count: int = 4, visited: set = None) -> List[str]:
    """Get random media thumbnails from album and its children"""
    if visited is None:
        visited = set()
    
    if album_id in visited:
        return []
    
    visited.add(album_id)
    
    # Get all media from this album and children (recursive)
    media_data = db.query(Media.id).join(
        blombooru_album_media,
        Media.id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id == album_id,
        Media.thumbnail_path.isnot(None)
    ).all()
    
    # Get media from child albums
    child_album_ids = db.query(blombooru_album_hierarchy.c.child_album_id).filter(
        blombooru_album_hierarchy.c.parent_album_id == album_id
    ).all()
    
    all_ids = [m[0] for m in media_data]
    
    for child_id_tuple in child_album_ids:
        child_ids = get_random_thumbnail_ids(child_id_tuple[0], db, count, visited)
        all_ids.extend(child_ids)
    
    # Remove duplicates and shuffle
    unique_ids = list(set(all_ids))
    random.shuffle(unique_ids)
    
    # Convert to API URLs
    return [f"/api/media/{mid}/thumbnail" for mid in unique_ids[:count]]

def get_random_thumbnail_ids(album_id: int, db: Session, count: int = 4, visited: set = None) -> List[int]:
    """Helper to get random media IDs for thumbnails (recursive)"""
    if visited is None:
        visited = set()
    
    if album_id in visited:
        return []
    
    visited.add(album_id)
    
    media_ids = db.query(Media.id).join(
        blombooru_album_media,
        Media.id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id == album_id,
        Media.thumbnail_path.isnot(None)
    ).all()
    
    child_album_ids = db.query(blombooru_album_hierarchy.c.child_album_id).filter(
        blombooru_album_hierarchy.c.parent_album_id == album_id
    ).all()
    
    all_ids = [m[0] for m in media_ids]
    
    for child_id_tuple in child_album_ids:
        child_ids = get_random_thumbnail_ids(child_id_tuple[0], db, count, visited)
        all_ids.extend(child_ids)
    
    return all_ids

def update_album_last_modified(album_id: int, db: Session):
    """Update last_modified timestamp for album"""
    db.execute(
        text("UPDATE blombooru_albums SET last_modified = :now WHERE id = :album_id"),
        {"now": datetime.now(), "album_id": album_id}
    )
    db.commit()

def get_parent_ids(album_id: int, db: Session) -> List[int]:
    """Get all parent album IDs (breadcrumb trail)"""
    parent_ids = []
    current_id = album_id
    visited = set()
    
    while current_id and current_id not in visited:
        visited.add(current_id)
        parent = db.query(blombooru_album_hierarchy.c.parent_album_id).filter(
            blombooru_album_hierarchy.c.child_album_id == current_id
        ).first()
        
        if parent:
            parent_ids.insert(0, parent[0])
            current_id = parent[0]
        else:
            break
    
    return parent_ids

def get_media_count(album_id: int, db: Session, visited: set = None) -> int:
    """Get total count of media in album and children (recursive)"""
    if visited is None:
        visited = set()
    
    if album_id in visited:
        return 0
    
    visited.add(album_id)
    
    # Count direct media
    direct_count = db.query(func.count(blombooru_album_media.c.media_id)).filter(
        blombooru_album_media.c.album_id == album_id
    ).scalar()
    
    # Count media in children
    child_album_ids = db.query(blombooru_album_hierarchy.c.child_album_id).filter(
        blombooru_album_hierarchy.c.parent_album_id == album_id
    ).all()
    
    total_count = direct_count
    for child_id_tuple in child_album_ids:
        total_count += get_media_count(child_id_tuple[0], db, visited)
    
    return total_count

def get_album_popular_tags(album_id: int, db: Session, limit: int = 20, visited: set = None) -> List[dict]:
    """Recursively aggregate and count tags from media in album and its children"""
    if visited is None:
        visited = set()
    
    if album_id in visited:
        return []
    
    visited.add(album_id)
    
    from ..models import Tag, blombooru_media_tags
    
    # Get all media IDs in this album and children
    def get_all_media_ids(aid: int, v: set) -> List[int]:
        if aid in v: return []
        v.add(aid)
        
        mids = [m[0] for m in db.query(blombooru_album_media.c.media_id).filter(
            blombooru_album_media.c.album_id == aid
        ).all()]
        
        child_aids = [c[0] for c in db.query(blombooru_album_hierarchy.c.child_album_id).filter(
            blombooru_album_hierarchy.c.parent_album_id == aid
        ).all()]
        
        for caid in child_aids:
            mids.extend(get_all_media_ids(caid, v))
        return mids

    all_media_ids = get_all_media_ids(album_id, set())
    
    if not all_media_ids:
        return []
    
    # Count tags for these media IDs
    tag_counts = db.query(
        Tag.id,
        Tag.name,
        Tag.category,
        func.count(blombooru_media_tags.c.tag_id).label('count')
    ).join(
        blombooru_media_tags,
        Tag.id == blombooru_media_tags.c.tag_id
    ).filter(
        blombooru_media_tags.c.media_id.in_(all_media_ids)
    ).group_by(
        Tag.id
    ).order_by(
        text('count DESC')
    ).limit(limit).all()
    
    return [
        {
            "id": tc.id,
            "name": tc.name,
            "category": tc.category,
            "count": tc.count
        } for tc in tag_counts
    ]

def get_bulk_album_metrics(album_ids: List[int], db: Session):
    """
    Efficiently compute recursive ratings and counts for a list of albums.
    Uses only a few queries regardless of the number of albums.
    """
    if not album_ids:
        return {}

    # 1. Fetch direct media ratings and counts for ALL albums
    direct_stats = db.query(
        blombooru_album_media.c.album_id,
        Media.rating,
        func.count(Media.id).label('count')
    ).join(Media, Media.id == blombooru_album_media.c.media_id).group_by(blombooru_album_media.c.album_id, Media.rating).all()
    
    album_data = {}
    for aid, rating, count in direct_stats:
        if aid not in album_data:
            album_data[aid] = {'ratings': set(), 'count': 0}
        album_data[aid]['ratings'].add(rating)
        album_data[aid]['count'] += count
    
    # 2. Fetch entire hierarchy
    hierarchies = db.query(blombooru_album_hierarchy).all()
    children_map = {}
    for pid, cid in hierarchies:
        if pid not in children_map:
            children_map[pid] = []
        children_map[pid].append(cid)
        
    # 3. Recursive computation with memoization
    memo = {}
    rating_priority = {RatingEnum.explicit: 3, RatingEnum.questionable: 2, RatingEnum.safe: 1}

    def compute(aid, visited):
        if aid in memo:
            return memo[aid]
        if aid in visited:
            return {'rating': RatingEnum.safe, 'count': 0}
        
        # Avoid circular references
        new_visited = visited | {aid}
        
        # Start with direct stats
        stats = album_data.get(aid, {'ratings': set(), 'count': 0})
        current_ratings = set(stats['ratings'])
        current_count = stats['count']
        
        # Add child stats
        for cid in children_map.get(aid, []):
            child_stats = compute(cid, new_visited)
            current_ratings.add(child_stats['rating'])
            current_count += child_stats['count']
            
        # Determine highest rating
        highest = RatingEnum.safe
        if current_ratings:
            highest = max(current_ratings, key=lambda r: rating_priority.get(r, 0))
            
        res = {'rating': highest, 'count': current_count}
        memo[aid] = res
        return res

    final_results = {}
    for aid in album_ids:
        final_results[aid] = compute(aid, set())
        
    return final_results
