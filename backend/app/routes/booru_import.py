from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
import tempfile
import requests
import hashlib
from pathlib import Path

from ..database import get_db
from ..auth import require_admin_mode
from ..models import Media, Tag, User, Album, blombooru_media_tags
from ..config import settings
from ..services.booru import get_client_for_url, BooruPost
from ..utils.media_processor import process_media_file, calculate_file_hash
from ..utils.thumbnail_generator import generate_thumbnail
from ..utils.media_helpers import get_unique_filename
from ..utils.cache import invalidate_media_cache, invalidate_tag_cache, invalidate_album_cache
from ..utils.album_utils import update_album_last_modified
from .media import get_or_create_tags, update_tag_counts

router = APIRouter(prefix="/api/booru-import", tags=["booru-import"])

class FetchRequest(BaseModel):
    url: str

class ImportRequest(BaseModel):
    url: str
    rating: Optional[str] = None
    tags: Optional[list[str]] = None
    source: Optional[str] = None
    album_ids: Optional[list[int]] = None
    auto_create_tags: bool = False
    category_hints: Optional[dict[str, str]] = None

@router.post("/fetch")
async def fetch_booru_post(
    req: FetchRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """
    Fetch metadata from a booru post URL.
    
    Returns post data (tags with categories, rating, source, file URLs)
    without downloading the media file.
    """
    client = get_client_for_url(req.url, db=db)
    if not client:
        raise HTTPException(
            status_code=400,
            detail="admin.media_management.booru_import.error_unsupported_url"
        )

    try:
        post = client.fetch_post_by_url(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.HTTPError as e:
        if e.response.status_code == 403:
            raise HTTPException(status_code=403, detail="admin.media_management.booru_import.error_access_denied_403")
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="admin.media_management.booru_import.error_post_not_found")
        raise HTTPException(status_code=502, detail=f"admin.media_management.booru_import.error_booru_api:::{str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"admin.media_management.booru_import.error_fetch_failed:::{str(e)}")

    return {
        "id": post.id,
        "tags": [{"name": t.name, "category": t.category} for t in post.tags],
        "rating": post.rating,
        "source": post.source,
        "file_url": post.file_url,
        "preview_url": post.preview_url,
        "filename": post.filename,
        "width": post.width,
        "height": post.height,
        "file_size": post.file_size,
        "score": post.score,
        "booru_url": post.booru_url,
    }

@router.post("/download")
async def download_and_import(
    req: ImportRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """
    Download media from a booru and import it into the library.
    
    Fetches the post metadata, downloads the media file, and processes
    it through the standard upload pipeline (hash check, thumbnails, etc.).
    """
    # Fetch post metadata
    client = get_client_for_url(req.url, db=db)
    if not client:
        raise HTTPException(
            status_code=400,
            detail="admin.media_management.booru_import.error_unsupported_url"
        )

    try:
        post = client.fetch_post_by_url(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.HTTPError as e:
        if e.response.status_code == 403:
            raise HTTPException(status_code=403, detail="admin.media_management.booru_import.error_access_denied_403")
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="admin.media_management.booru_import.error_post_not_found")
        raise HTTPException(status_code=502, detail=f"admin.media_management.booru_import.error_booru_api:::{str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"admin.media_management.booru_import.error_fetch_failed:::{str(e)}")

    if not post.file_url:
        raise HTTPException(status_code=400, detail="admin.media_management.booru_import.error_no_file")

    # Download media file to temp location
    try:
        if client and hasattr(client, "session"):
            response = client.session.get(post.file_url, timeout=60, stream=True)
        else:
            response = requests.get(post.file_url, timeout=60, stream=True)

        response.raise_for_status()
    except requests.HTTPError as e:
        if e.response.status_code == 403:
            raise HTTPException(status_code=403, detail="admin.media_management.booru_import.error_download_403")
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="admin.media_management.booru_import.error_file_not_found")
        raise HTTPException(status_code=502, detail=f"admin.media_management.booru_import.error_download_api:::{str(e)}")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"admin.media_management.booru_import.error_download_failed:::{str(e)}")

    try:
        suffix = Path(post.filename).suffix or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in response.iter_content(chunk_size=8192):
                tmp.write(chunk)
            tmp_path = Path(tmp.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"admin.media_management.booru_import.error_save_failed:::{str(e)}")

    try:
        # Check for duplicates
        file_hash = calculate_file_hash(tmp_path)
        existing = db.query(Media).filter(Media.hash == file_hash).first()
        if existing:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=409,
                detail=f"Media already exists (duplicate of {existing.filename})"
            )

        unique_filename = get_unique_filename(settings.ORIGINAL_DIR, post.filename)
        file_path = settings.ORIGINAL_DIR / unique_filename
        
        import shutil
        shutil.move(str(tmp_path), str(file_path))

        metadata = process_media_file(file_path)

        thumbnail_name = Path(unique_filename).stem
        thumbnail_filename = f"{thumbnail_name}.jpg"
        thumbnail_path = settings.THUMBNAIL_DIR / thumbnail_filename

        thumbnail_generated = generate_thumbnail(
            file_path,
            thumbnail_path,
            metadata['file_type']
        )

        relative_path = file_path.relative_to(settings.BASE_DIR)
        relative_thumb = thumbnail_path.relative_to(settings.BASE_DIR) if thumbnail_generated else None

        final_rating = req.rating or post.rating
        final_source = req.source if req.source is not None else (post.source or post.booru_url)
        final_tags = req.tags if req.tags is not None else [t.name for t in post.tags]

        media = Media(
            filename=unique_filename,
            path=str(relative_path),
            thumbnail_path=str(relative_thumb) if relative_thumb else None,
            hash=file_hash,
            file_type=metadata['file_type'],
            mime_type=metadata['mime_type'],
            file_size=metadata['file_size'],
            width=metadata['width'],
            height=metadata['height'],
            duration=metadata['duration'],
            rating=final_rating,
            source=final_source if final_source else None,
        )

        # Handle tags
        tag_ids_to_update = []
        if final_tags:
            category_hints = None
            if req.auto_create_tags:
                category_hints = req.category_hints or {}
                for t in post.tags:
                    if t.name.lower() not in category_hints:
                        category_hints[t.name.lower()] = t.category

            tag_list = [t.strip() for t in final_tags if t.strip()]
            media.tags = get_or_create_tags(db, tag_list, category_hints=category_hints)
            tag_ids_to_update = [tag.id for tag in media.tags]

        # Handle albums
        affected_album_ids = []
        if req.album_ids:
            albums = db.query(Album).filter(Album.id.in_(req.album_ids)).all()
            media.albums = albums
            affected_album_ids = [album.id for album in albums]

        db.add(media)
        db.commit()
        db.refresh(media)

        if tag_ids_to_update:
            update_tag_counts(db, tag_ids_to_update)
            db.commit()

        if affected_album_ids:
            for a_id in affected_album_ids:
                update_album_last_modified(a_id, db)
            db.commit()
            invalidate_album_cache()

        db.refresh(media)

        invalidate_media_cache()
        invalidate_tag_cache()

        from ..schemas import MediaResponse
        return MediaResponse.model_validate(media)

    except HTTPException:
        raise
    except Exception as e:
        # Clean up on error
        if 'tmp_path' in locals() and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        if 'file_path' in locals() and file_path.exists():
            file_path.unlink(missing_ok=True)
        if 'thumbnail_path' in locals() and thumbnail_path.exists():
            thumbnail_path.unlink(missing_ok=True)

        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"admin.media_management.booru_import.import_error:::{str(e)}")

@router.get("/proxy-image")
async def proxy_image(
    url: str, 
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """
    Proxy an image request through the backend to bypass CORS.
    """
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="admin.media_management.booru_import.error_invalid_url")
    
    try:
        client = get_client_for_url(url, db=db)
        if client:
            external_resp = client.session.get(url, stream=True, timeout=60)
        else:
            external_resp = requests.get(url, stream=True, timeout=60, headers={"User-Agent": "Blombooru/1.0 (booru-import)"})
            
        if external_resp.status_code == 403:
            raise HTTPException(status_code=403, detail="admin.media_management.booru_import.error_image_403")
        if external_resp.status_code == 404:
            raise HTTPException(status_code=404, detail="admin.media_management.booru_import.error_image_404")
             
        external_resp.raise_for_status()
        
        return StreamingResponse(
            external_resp.iter_content(chunk_size=8192),
            media_type=external_resp.headers.get("content-type"),
            headers={"Cache-Control": "public, max-age=3600"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"admin.media_management.booru_import.error_proxy_failed:::{str(e)}")
