from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List
import uuid
from ..database import get_db
from ..auth import require_admin_mode, get_current_user
from ..models import Album, Media, User, blombooru_album_media
from ..schemas import AlbumResponse, AlbumCreate, AlbumUpdate, MediaResponse

router = APIRouter(prefix="/api/albums", tags=["albums"])

@router.get("/", response_model=List[AlbumResponse])
async def get_albums(db: Session = Depends(get_db)):
    """Get all albums"""
    albums = db.query(Album).order_by(Album.is_system.desc(), Album.name).all()
    
    # Add media count to each album
    result = []
    for album in albums:
        album_dict = AlbumResponse.model_validate(album).model_dump()
        album_dict['media_count'] = len(album.media)
        result.append(album_dict)
    
    return result

@router.get("/{album_id}", response_model=AlbumResponse)
async def get_album(album_id: int, db: Session = Depends(get_db)):
    """Get single album"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    album_dict = AlbumResponse.model_validate(album).model_dump()
    album_dict['media_count'] = len(album.media)
    return album_dict

@router.get("/{album_id}/media")
async def get_album_media(album_id: int, page: int = 1, limit: int = 30, db: Session = Depends(get_db)):
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    q = db.query(Media).join(blombooru_album_media, Media.id == blombooru_album_media.c.media_id) \
        .filter(blombooru_album_media.c.album_id == album_id) \
        .order_by(desc(Media.uploaded_at)) \
        .distinct(Media.id)  # important

    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()
    return {
        "album": AlbumResponse.model_validate(album),
        "items": [MediaResponse.model_validate(m) for m in items],
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit)
    }

@router.post("/", response_model=AlbumResponse)
async def create_album(
    album_data: AlbumCreate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Create new album"""
    from ..routes.media import get_or_create_tags
    
    album = Album(
        name=album_data.name,
        description=album_data.description,
        rating=album_data.rating
    )
    
    if album_data.tags:
        album.tags = get_or_create_tags(db, album_data.tags)
    
    db.add(album)
    db.commit()
    db.refresh(album)
    
    album_dict = AlbumResponse.model_validate(album).model_dump()
    album_dict['media_count'] = 0
    return album_dict

@router.patch("/{album_id}", response_model=AlbumResponse)
async def update_album(
    album_id: int,
    updates: AlbumUpdate,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Update album"""
    from ..routes.media import get_or_create_tags
    
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    if album.is_system and updates.name:
        raise HTTPException(status_code=400, detail="Cannot rename system album")
    
    if updates.name:
        album.name = updates.name
    if updates.description is not None:
        album.description = updates.description
    if updates.rating:
        album.rating = updates.rating
    if updates.cover_media_id is not None:
        album.cover_media_id = updates.cover_media_id
    if updates.tags is not None:
        album.tags = get_or_create_tags(db, updates.tags)
    
    db.commit()
    db.refresh(album)
    
    album_dict = AlbumResponse.model_validate(album).model_dump()
    album_dict['media_count'] = len(album.media)
    return album_dict

@router.delete("/{album_id}")
async def delete_album(
    album_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Delete album"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    if album.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system album")
    
    db.delete(album)
    db.commit()
    
    return {"message": "Album deleted successfully"}

@router.post("/{album_id}/media/{media_id}")
async def add_media_to_album(
    album_id: int,
    media_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Add media to album"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Check if already in album to prevent duplicates
    from sqlalchemy import exists
    already_exists = db.query(
        exists().where(
            and_(
                blombooru_album_media.c.album_id == album_id,
                blombooru_album_media.c.media_id == media_id
            )
        )
    ).scalar()
    
    if already_exists:
        return {"message": "Media already in album", "added": False}
    
    # Use raw insert to ensure no duplicates
    db.execute(
        blombooru_album_media.insert().values(
            album_id=album_id,
            media_id=media_id,
            position=0
        )
    )
    db.commit()
    
    return {"message": "Media added to album", "added": True}

@router.delete("/{album_id}/media/{media_id}")
async def remove_media_from_album(
    album_id: int,
    media_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Remove media from album"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Remove from album
    if media in album.media:
        album.media.remove(media)
        db.commit()
        return {"message": "Media removed from album"}
    else:
        raise HTTPException(status_code=404, detail="Media not in this album")

@router.post("/{album_id}/share")
async def share_album(
    album_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Create share link for album"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    if not album.is_shared:
        album.is_shared = True
        album.share_uuid = str(uuid.uuid4())
        db.commit()
    
    return {"share_url": f"/shared/{album.share_uuid}"}

@router.delete("/{album_id}/share")
async def unshare_album(
    album_id: int,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Remove share link for album"""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    album.is_shared = False
    album.share_uuid = None
    db.commit()
    
    return {"message": "Share removed"}
