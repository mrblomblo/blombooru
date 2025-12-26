from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc, func, text, or_, and_
from typing import List, Optional
from datetime import datetime
import random

from ..database import get_db
from ..models import Album, Media, RatingEnum, blombooru_album_media, blombooru_album_hierarchy
from ..schemas import AlbumCreate, AlbumUpdate, AlbumResponse, AlbumListResponse, MediaIds
from ..auth import get_current_admin_user, require_admin_mode, User
from ..config import settings
from ..utils.album_utils import (
    get_album_rating,
    get_album_tags,
    get_random_thumbnails,
    update_album_last_modified,
    get_parent_ids,
    get_media_count,
    get_album_popular_tags
)

router = APIRouter(prefix="/api/albums", tags=["albums"])

# API Endpoints

@router.get("", response_model=dict)
async def get_albums(
    page: int = 1,
    limit: int = Query(None),
    sort: Optional[str] = Query("created_at"),
    order: Optional[str] = Query("desc"),
    rating: Optional[str] = None,
    root_only: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Get paginated album list"""
    if limit is None:
        limit = settings.get_items_per_page()
    
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
    
    # Get all albums matching root_only and sorting to filter by computed rating
    all_albums = query.all()
    
    # Filter and build list
    filtered_albums = []
    for album in all_albums:
        album_rating = get_album_rating(album.id, db)
        
        # Apply rating filter (max rating logic)
        if rating and rating != "explicit":
            if rating == "safe" and album_rating != RatingEnum.safe:
                continue
            if rating == "questionable" and album_rating == RatingEnum.explicit:
                continue
        
        filtered_albums.append((album, album_rating))
    
    total = len(filtered_albums)
    
    # Paginate the filtered list
    start = (page - 1) * limit
    end = start + limit
    paginated_albums = filtered_albums[start:end]
    
    # Build response
    album_list = []
    for album, album_rating in paginated_albums:
        thumbnails = get_random_thumbnails(album.id, db, count=4)
        media_count = get_media_count(album.id, db)
        
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
        "pages": (total + limit - 1) // limit if limit > 0 else 0
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
    
    return await get_album(album_id, db)

@router.delete("/{album_id}")
async def delete_album(
    album_id: int,
    cascade: bool = Query(False),
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
    
    return {"message": "Media removed from album"}

@router.get("/{album_id}/contents")
async def get_album_contents(
    album_id: int,
    page: int = 1,
    limit: int = Query(None),
    rating: Optional[str] = Query(None),
    sort: str = Query("uploaded_at"),
    order: str = Query("desc"),
    db: Session = Depends(get_db)
):
    """Get album contents (media + sub-albums, paginated)"""
    # Normalize order string
    sort_order = order.lower() if order else "desc"
    
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    if limit is None:
        limit = settings.get_items_per_page()
    
    # --- 1. MEDIA ITEMS ---
    from ..schemas import MediaResponse
    
    # Start query
    media_query = db.query(Media).join(
        blombooru_album_media,
        Media.id == blombooru_album_media.c.media_id
    ).filter(
        blombooru_album_media.c.album_id == album_id
    ).options(joinedload(Media.tags))
    
    # Filter Rating
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

    # Execute Media Query
    total_media = media_query.count()
    media_items = media_query.offset((page - 1) * limit).limit(limit).all()
    
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
    rating_priority = {RatingEnum.explicit: 3, RatingEnum.questionable: 2, RatingEnum.safe: 1}
    max_rating_val = rating_priority.get(RatingEnum[rating] if rating in RatingEnum.__members__ else RatingEnum.explicit, 3)
    
    for child in child_albums:
        child_rating = get_album_rating(child.id, db)
        
        # Skip if rating is too high for current filter
        if rating and rating_priority.get(child_rating, 1) > max_rating_val:
            continue
            
        thumbnails = get_random_thumbnails(child.id, db, count=4)
        media_count = get_media_count(child.id, db)
        
        child_album_list.append(AlbumListResponse(
            id=child.id,
            name=child.name,
            last_modified=child.last_modified,
            thumbnail_paths=thumbnails,
            rating=child_rating,
            media_count=media_count
        ))
    
    return {
        "media": [MediaResponse.model_validate(m) for m in media_items],
        "albums": child_album_list,
        "total_media": total_media,
        "page": page,
        "limit": limit,
        "pages": (total_media + limit - 1) // limit if limit > 0 else 0
    }

@router.get("/{album_id}/tags")
async def get_album_tags_endpoint(
    album_id: int,
    limit: int = Query(20),
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
    for child in children:
        thumbnails = get_random_thumbnails(child.id, db, count=4)
        child_rating = get_album_rating(child.id, db)
        media_count = get_media_count(child.id, db)
        
        result.append(AlbumListResponse(
            id=child.id,
            name=child.name,
            last_modified=child.last_modified,
            thumbnail_paths=thumbnails,
            rating=child_rating,
            media_count=media_count
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
