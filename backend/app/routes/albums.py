from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import desc, asc, func, text, or_, and_
from typing import List, Optional
from datetime import datetime
import random
from ..database import get_db
from ..models import Album, Media, RatingEnum, blombooru_album_media, blombooru_album_hierarchy
from ..schemas import AlbumCreate, AlbumUpdate, AlbumResponse, AlbumListResponse, MediaIds
from ..auth import get_current_admin_user, require_admin_mode, User
from ..config import settings
from ..utils.cache import cache_response, invalidate_album_cache
from ..utils.search_parser import parse_search_query, apply_search_criteria
from ..utils.album_utils import (
    get_album_rating,
    get_album_tags,
    get_random_thumbnails,
    update_album_last_modified,
    get_parent_ids,
    get_media_count,
    get_album_popular_tags,
    get_bulk_album_metrics
)

router = APIRouter(prefix="/api/albums", tags=["albums"])


def get_effective_limit(limit: Optional[int]) -> int:
    """Get effective limit, falling back to settings if not provided or invalid."""
    if limit is None or limit <= 0:
        return settings.get_items_per_page()
    return limit


@router.get("", response_model=dict)
@cache_response(expire=3600, key_prefix="album_list")
async def get_albums(
    request: Request,
    page: int = 1,
    limit: Optional[int] = Query(default=None),
    sort: Optional[str] = Query(default="created_at"),
    order: Optional[str] = Query(default="desc"),
    rating: Optional[str] = None,
    root_only: bool = Query(default=False),
    db: Session = Depends(get_db)
):
    """Get paginated album list"""
    limit = get_effective_limit(limit)
    
    # Build query
    query = db.query(Album)
    
    if root_only:
        # Only show albums that are not children of any other album
        query = query.filter(~Album.id.in_(db.query(blombooru_album_hierarchy.c.child_album_id)))
    
    # Apply sorting
    sort_column = Album.created_at
    if sort == "name":
        sort_column = Album.name
    elif sort == "last_modified":
        sort_column = Album.last_modified
    
    if order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
    
    # Get all albums
    all_albums = query.all()
    all_album_ids = [a.id for a in all_albums]
    all_metrics = get_bulk_album_metrics(all_album_ids, db)
    
    # Filter and build list
    filtered_albums = []
    for album in all_albums:
        metrics = all_metrics.get(album.id, {'rating': RatingEnum.safe, 'count': 0})
        album_rating = metrics['rating']
        
        # Apply rating filter (max rating logic)
        if rating and rating != "explicit":
            if rating == "safe" and album_rating != RatingEnum.safe:
                continue
            if rating == "questionable" and album_rating == RatingEnum.explicit:
                continue
        
        filtered_albums.append((album, album_rating, metrics['count']))
    
    total = len(filtered_albums)
    
    # Paginate the filtered list
    start = (page - 1) * limit
    end = start + limit
    paginated_albums = filtered_albums[start:end]
    
    # Build response
    album_list = []
    for album, album_rating, media_count in paginated_albums:
        thumbnails = get_random_thumbnails(album.id, db, count=4)
        
        album_list.append(AlbumListResponse(
            id=album.id,
            name=album.name,
            last_modified=album.last_modified,
            thumbnail_paths=thumbnails,
            rating=album_rating,
            media_count=media_count
        ))
    
    return {
        "items": album_list,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit)
    }

@router.get("/{album_id}", response_model=AlbumResponse)
async def get_album(
    album_id: int,
    db: Session = Depends(get_db)
):
    """Get single album details"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    # Compute fields
    album_rating = get_album_rating(album.id, db)
    media_count = get_media_count(album.id, db)
    children_count = db.query(func.count(blombooru_album_hierarchy.c.child_album_id)).filter(
        blombooru_album_hierarchy.c.parent_album_id == album_id
    ).scalar()
    parent_ids = get_parent_ids(album.id, db)
    
    return AlbumResponse(
        id=album.id,
        name=album.name,
        created_at=album.created_at,
        updated_at=album.updated_at,
        last_modified=album.last_modified,
        media_count=media_count,
        children_count=children_count,
        rating=album_rating,
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
    
    # Create album
    new_album = Album(name=album_data.name)
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
    """Update album name/parent (admin only)"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    # Update name
    if album_data.name is not None:
        album.name = album_data.name
    
    # Update parent relationship
    if album_data.parent_album_id is not None:
        # Check for circular reference
        if album_data.parent_album_id == album_id:
            raise HTTPException(status_code=400, detail="Album cannot be its own parent")
        
        # Check if new parent exists
        if album_data.parent_album_id:
            parent = db.query(Album).filter(Album.id == album_data.parent_album_id).first()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent album not found")
        
        # Remove old parent relationship
        db.execute(
            blombooru_album_hierarchy.delete().where(
                blombooru_album_hierarchy.c.child_album_id == album_id
            )
        )
        
        # Add new parent relationship
        if album_data.parent_album_id:
            db.execute(
                blombooru_album_hierarchy.insert().values(
                    parent_album_id=album_data.parent_album_id,
                    child_album_id=album_id
                )
            )
    
    db.commit()
    db.refresh(album)
    
    # Invalidate cache
    invalidate_album_cache()
    
    return await get_album(album_id, db)

@router.delete("/{album_id}")
async def delete_album(
    album_id: int,
    cascade: bool = Query(default=False),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Delete album (admin only)"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    if cascade:
        # Delete child albums recursively
        def delete_children(parent_id: int):
            children = db.query(blombooru_album_hierarchy.c.child_album_id).filter(
                blombooru_album_hierarchy.c.parent_album_id == parent_id
            ).all()
            
            for child_tuple in children:
                child_id = child_tuple[0]
                delete_children(child_id)
                child_album = db.query(Album).filter(Album.id == child_id).first()
                if child_album:
                    db.delete(child_album)
        
        delete_children(album_id)
    else:
        # Just remove parent relationships for children (orphan them)
        db.execute(
            blombooru_album_hierarchy.delete().where(
                blombooru_album_hierarchy.c.parent_album_id == album_id
            )
        )
    
    db.delete(album)
    db.commit()
    
    # Invalidate cache
    invalidate_album_cache()
    
    return {"message": "Album deleted successfully"}

@router.post("/{album_id}/media")
async def add_media_to_album(
    album_id: int,
    data: MediaIds,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Add media items to album (bulk operation, admin only)"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    added_count = 0
    for media_id in data.media_ids:
        media = db.query(Media).filter(Media.id == media_id).first()
        if not media:
            continue
        
        # Check if already in album
        existing = db.query(blombooru_album_media).filter(
            and_(
                blombooru_album_media.c.album_id == album_id,
                blombooru_album_media.c.media_id == media_id
            )
        ).first()
        
        if not existing:
            db.execute(
                blombooru_album_media.insert().values(
                    album_id=album_id,
                    media_id=media_id
                )
            )
            added_count += 1
    
    # Update last_modified
    update_album_last_modified(album_id, db)
    
    # Invalidate cache
    invalidate_album_cache()
    
    return {"message": f"Added {added_count} media item(s) to album"}

@router.delete("/{album_id}/media")
async def remove_media_from_album(
    album_id: int,
    data: MediaIds,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Remove media items from album (bulk operation, admin only)"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    db.execute(
        blombooru_album_media.delete().where(
            and_(
                blombooru_album_media.c.album_id == album_id,
                blombooru_album_media.c.media_id.in_(data.media_ids)
            )
        )
    )
    
    # Update last_modified
    update_album_last_modified(album_id, db)
    
    # Invalidate cache
    invalidate_album_cache()
    
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
    sort: str = Query(default="uploaded_at"),
    order: str = Query(default="desc"),
    db: Session = Depends(get_db)
):
    """Get album contents (media + sub-albums, paginated)"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    # Get effective limit from settings if not provided
    limit = get_effective_limit(limit)
    
    # Normalize order string
    sort_order = order.lower() if order else "desc"
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    
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
    if q:
        parsed = parse_search_query(q)
        
        # Merge rating filter into parsed query if provided
        if rating and rating != "explicit":
            rating_value = "safe" if rating == "safe" else "safe,questionable"
            if 'rating' not in parsed['meta']:
                parsed['meta']['rating'] = []
            parsed['meta']['rating'].append({'value': rating_value, 'negated': False})
        
        # Apply search criteria to media query
        media_query = apply_search_criteria(media_query, parsed, db)
    else:
        # Filter Rating (only if no tag query provided)
        if rating and rating != "explicit":
            allowed_ratings = {
                "safe": [RatingEnum.safe],
                "questionable": [RatingEnum.safe, RatingEnum.questionable]
            }
            media_query = media_query.filter(Media.rating.in_(allowed_ratings.get(rating, [])))
    
    # Sort Media
    media_sort_mapping = {
        'uploaded_at': Media.id,
        'filename': Media.filename,
        'name': Media.filename,
        'file_size': Media.file_size,
        'file_type': Media.file_type,
        'last_modified': Media.id
    }
    
    # Default to Media.id if key not found
    media_sort_column = media_sort_mapping.get(sort, Media.id)
    
    # Apply Sort using column methods
    if sort_order == "asc":
        media_query = media_query.order_by(media_sort_column.asc())
    else:
        media_query = media_query.order_by(media_sort_column.desc())

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
    
    # Sort Albums
    album_sort_mapping = {
        'name': Album.name,
        'filename': Album.name,
        'last_modified': Album.last_modified,
        'uploaded_at': Album.created_at
    }
    
    album_sort_column = album_sort_mapping.get(sort, Album.created_at)
    
    # Apply Sort using column methods
    if sort_order == "asc":
        child_albums_query = child_albums_query.order_by(album_sort_column.asc())
    else:
        child_albums_query = child_albums_query.order_by(album_sort_column.desc())

    child_albums = child_albums_query.all()
    
    # Build Album Response List (with rating logic)
    child_album_list = []
    
    if child_albums:
        child_ids = [c.id for c in child_albums]
        all_metrics = get_bulk_album_metrics(child_ids, db)
        
        rating_priority = {RatingEnum.explicit: 3, RatingEnum.questionable: 2, RatingEnum.safe: 1}
        # Safely get max_rating_val based on the rating filter
        target_rating = RatingEnum(rating) if rating and rating in [r.value for r in RatingEnum] else RatingEnum.explicit
        max_rating_val = rating_priority.get(target_rating, 3)
        
        for child in child_albums:
            metrics = all_metrics.get(child.id, {'rating': RatingEnum.safe, 'count': 0})
            child_rating = metrics['rating']
            
            # Skip if rating is too high for current filter
            if rating and rating_priority.get(child_rating, 1) > max_rating_val:
                continue
                
            thumbnails = get_random_thumbnails(child.id, db, count=4)
            media_count = metrics['count']
            
            child_album_list.append(AlbumListResponse(
                id=child.id,
                name=child.name,
                last_modified=child.last_modified,
                thumbnail_paths=thumbnails,
                rating=child_rating,
                media_count=media_count
            ))
    
    # Calculate total pages
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
    """Get popular tags within an album and its children"""
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
    """Get direct child albums"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    children = db.query(Album).join(
        blombooru_album_hierarchy,
        Album.id == blombooru_album_hierarchy.c.child_album_id
    ).filter(
        blombooru_album_hierarchy.c.parent_album_id == album_id
    ).all()
    
    result = []
    if children:
        child_ids = [c.id for c in children]
        all_metrics = get_bulk_album_metrics(child_ids, db)
        
        for child in children:
            metrics = all_metrics.get(child.id, {'rating': RatingEnum.safe, 'count': 0})
            thumbnails = get_random_thumbnails(child.id, db, count=4)
            
            result.append(AlbumListResponse(
                id=child.id,
                name=child.name,
                last_modified=child.last_modified,
                thumbnail_paths=thumbnails,
                rating=metrics['rating'],
                media_count=metrics['count']
            ))
    
    return result

@router.get("/{album_id}/parents")
async def get_parent_albums(
    album_id: int,
    db: Session = Depends(get_db)
):
    """Get parent album chain (breadcrumb)"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    parent_ids = get_parent_ids(album_id, db)
    parents = []
    
    for parent_id in parent_ids:
        parent = db.query(Album).filter(Album.id == parent_id).first()
        if parent:
            parents.append({
                "id": parent.id,
                "name": parent.name
            })
    
    return {"parents": parents}
