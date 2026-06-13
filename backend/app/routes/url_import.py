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

router = APIRouter(prefix="/api/media/url-import", tags=["url-import"])

class FetchRequest(BaseModel):
    url: str

class ImportRequest(BaseModel):
    url: str
    rating: Optional[RatingEnum] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None
    album_ids: Optional[List[int]] = None
    category_hints: Optional[dict[str, str]] = None

@router.post("/fetch")
async def fetch_media_url(
    req: FetchRequest,
    current_user: User = Depends(require_admin_mode),
):
    """Probe a direct media URL and return metadata without downloading the full file."""
    try:
        return probe_media_url(req.url)
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
            response.iter_content(chunk_size=8192),
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
    Download media from a direct URL and import it into the library in one step.

    Only ``url`` is required; all other fields are optional. Authenticated via
    admin session or API key (for browser extensions and other API clients).
    """
    from .media import process_and_save_media

    tmp_path: Optional[Path] = None
    file_path: Optional[Path] = None

    try:
        tmp_path, filename = download_media_to_temp(req.url)

        unique_filename = get_unique_filename(settings.ORIGINAL_DIR, filename)
        file_path = settings.ORIGINAL_DIR / unique_filename
        shutil.move(str(tmp_path), str(file_path))
        tmp_path = None

        rating = req.rating if req.rating is not None else RatingEnum.safe
        source = req.source if req.source is not None else req.url

        tags_str = ""
        if req.tags:
            tags_str = " ".join(t.strip() for t in req.tags if t and t.strip())

        album_ids_str = None
        if req.album_ids:
            album_ids_str = ",".join(str(aid) for aid in req.album_ids)

        category_hints_str = None
        if req.category_hints:
            category_hints_str = json.dumps(req.category_hints)

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
            )
        except HTTPException as e:
            if e.status_code == 409 and file_path.exists():
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