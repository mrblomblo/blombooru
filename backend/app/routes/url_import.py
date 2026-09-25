import json
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_admin_mode
from ..config import settings
from ..database import get_db
from ..enums import RatingEnum
from ..models import User
from ..schemas import MediaResponse
from ..utils.logger import logger
from ..utils.media_helpers import get_unique_filename
from ..utils.request_helpers import safe_error_detail
from ..utils.url_fetch import UrlFetchError, download_media_to_temp, fetch_media_stream, probe_media_url
from ..services.booru import get_client_for_url

router = APIRouter(prefix="/api/media/url-import", tags=["url-import"])

def _stream_with_cleanup(response, chunk_size: int = 8192):
    try:
        yield from response.iter_content(chunk_size=chunk_size)
    finally:
        response.close()

class FetchRequest(BaseModel):
    url: str

class ImportRequest(BaseModel):
    url: str
    rating: Optional[RatingEnum] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None
    album_ids: Optional[List[int]] = None
    category_hints: Optional[dict[str, str]] = None
    auto_create_tags: bool = False

@router.post("/fetch")
async def fetch_media_url(
    req: FetchRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """Probe a direct media URL or a booru URL and return metadata without downloading the full file."""
    # Try Booru fetch first
    client = get_client_for_url(req.url, db=db)
    if client:
        try:
            import requests
            from .booru_import import _enrich_post_tags_with_db_categories
            post = client.fetch_post_by_url(req.url)
            _enrich_post_tags_with_db_categories(post, db)
            
            return {
                "is_booru_post": True,
                "id": post.id,
                "tags": [{"name": t.name, "category": t.category, "is_new": getattr(t, "is_new", True)} for t in post.tags],
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
                "description": post.description,
            }
        except Exception as e:
            logger.warning(f"Booru fetch failed for {req.url}, falling back to direct probe: {e}")
            try:
                data = probe_media_url(req.url)
                data["is_booru_post"] = False
                return data
            except Exception:
                pass
            if isinstance(e, requests.HTTPError):
                if e.response.status_code == 403:
                    raise HTTPException(status_code=403, detail="admin.media_management.booru_import.error_access_denied_403")
                if e.response.status_code == 404:
                    raise HTTPException(status_code=404, detail="admin.media_management.booru_import.error_post_not_found")
            raise HTTPException(
                status_code=500,
                detail=f"admin.media_management.booru_import.error_fetch_failed:::{safe_error_detail('Fetch failed', e)}",
            )

    # Fallback to direct media probe
    try:
        data = probe_media_url(req.url)
        data["is_booru_post"] = False
        return data
    except UrlFetchError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"admin.media_management.url_import.error_fetch_failed:::{safe_error_detail('Fetch failed', e)}",
        )

@router.get("/proxy")
async def proxy_media_url(
    url: str = Query(...),
    current_user: User = Depends(require_admin_mode),
):
    """Proxy a direct media URL through the backend to bypass CORS restrictions."""
    try:
        response, content_type = fetch_media_stream(url)
        return StreamingResponse(
            _stream_with_cleanup(response),
            media_type=content_type,
            headers={"Cache-Control": "no-store"},
        )
    except UrlFetchError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"admin.media_management.url_import.error_proxy_failed:::{safe_error_detail('Proxy failed', e)}",
        )

@router.post("/import", response_model=MediaResponse)
async def import_media_url(
    req: ImportRequest,
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db),
):
    """
    Download media from a direct URL or booru URL and import it into the library in one step.

    Only ``url`` is required; all other fields are optional. Authenticated via
    admin session or API key (for browser extensions and other API clients).
    """
    from .media import process_and_save_media

    tmp_path: Optional[Path] = None
    file_path: Optional[Path] = None

    booru_post = None
    client = get_client_for_url(req.url, db=db)
    if client:
        try:
            from .booru_import import _enrich_post_tags_with_db_categories
            booru_post = client.fetch_post_by_url(req.url)
            _enrich_post_tags_with_db_categories(booru_post, db)
        except Exception as e:
            logger.warning(f"Failed to fetch booru metadata for {req.url}, falling back to raw url import: {e}")

    try:
        download_url = booru_post.file_url if booru_post and booru_post.file_url else req.url
        tmp_path, filename = download_media_to_temp(download_url)
        
        # Prefer booru filename if available and different
        if booru_post and booru_post.filename:
            filename = booru_post.filename

        unique_filename = get_unique_filename(settings.ORIGINAL_DIR, filename)
        file_path = settings.ORIGINAL_DIR / unique_filename
        import shutil
        shutil.move(str(tmp_path), str(file_path))
        tmp_path = None

        rating = req.rating
        if rating is None:
            rating = RatingEnum(booru_post.rating) if booru_post and booru_post.rating else RatingEnum.safe

        source = req.source
        if source is None:
            source = booru_post.source or booru_post.booru_url if booru_post else req.url

        tags_str = ""
        if req.tags is not None:
            tags_str = " ".join(t.strip() for t in req.tags if t and t.strip())
        elif booru_post and booru_post.tags:
            tags_str = " ".join(t.name for t in booru_post.tags)

        album_ids_str = None
        if req.album_ids:
            album_ids_str = ",".join(str(aid) for aid in req.album_ids)

        category_hints_str = None
        if req.category_hints:
            import json
            category_hints_str = json.dumps(req.category_hints)
        elif req.auto_create_tags and booru_post and booru_post.tags:
            import json
            hints = {t.name.lower(): t.category for t in booru_post.tags}
            category_hints_str = json.dumps(hints)

        description = None
        if booru_post and booru_post.description:
            description = booru_post.description

        try:
            return process_and_save_media(
                db=db,
                file_path=file_path,
                unique_filename=unique_filename,
                rating=rating,
                tags=tags_str,
                album_ids=album_ids_str,
                source=source,
                category_hints=category_hints_str,
                description=description,
            )
        except HTTPException:
            if file_path and file_path.exists():
                file_path.unlink(missing_ok=True)
            raise

    except UrlFetchError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        if file_path and file_path.exists():
            file_path.unlink(missing_ok=True)
        logger.error(f"Error importing media from URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"admin.media_management.url_import.error_import_failed:::{safe_error_detail('Import failed', e)}",
        )
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
