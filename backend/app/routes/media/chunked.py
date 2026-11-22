import shutil
import uuid
from pathlib import Path
from typing import Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ...auth import require_admin_mode
from ...config import settings
from ...database import get_db
from ...enums import RatingEnum
from ...models import User
from ...schemas import MediaResponse
from ...utils.format_registry import format_registry
from ...utils.logger import logger
from ...utils.media_helpers import get_unique_filename
from ...utils.request_helpers import safe_error_detail
from .ingestion import process_and_save_media

router = APIRouter()

ARCHIVE_CHUNKS_DIR = settings.CACHE_DIR / "archive-chunks"
ARCHIVE_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

# Max chunk size: 99MB (CloudFlare compatible)
MAX_CHUNK_SIZE = 99 * 1024 * 1024

def cleanup_archive_chunks(max_age_seconds: int = 0):
    """Remove leftover chunk directories.

    Args:
        max_age_seconds: Only remove directories older than this many seconds.
                         0 means remove everything (used on startup).
    """
    import time

    if not ARCHIVE_CHUNKS_DIR.exists():
        return

    now = time.time()
    for child in ARCHIVE_CHUNKS_DIR.iterdir():
        if child.is_dir():
            if max_age_seconds > 0:
                try:
                    age = now - child.stat().st_mtime
                    if age < max_age_seconds:
                        continue
                except OSError:
                    pass
            shutil.rmtree(child, ignore_errors=True)

@router.post("/archive-chunk")
async def upload_archive_chunk(
    file: UploadFile = File(...),
    upload_id: Optional[str] = Form(None),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
    current_user: User = Depends(require_admin_mode)
):
    """Receive a single chunk of an archive upload."""
    import re

    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=400, detail="Invalid chunk_index")

    if chunk_index == 0 and not upload_id:
        upload_id = str(uuid.uuid4())
    elif not upload_id or not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid or missing upload_id")

    contents = await file.read()
    if len(contents) > MAX_CHUNK_SIZE:
        raise HTTPException(status_code=400, detail=f"Chunk too large (max {MAX_CHUNK_SIZE // (1024 * 1024)}MB)")

    chunk_dir = ARCHIVE_CHUNKS_DIR / upload_id
    chunk_dir.mkdir(parents=True, exist_ok=True)

    # Store metadata on first chunk
    meta_path = chunk_dir / "meta.json"
    if chunk_index == 0:
        import json as _json
        with open(meta_path, 'w') as f:
            _json.dump({"filename": filename, "total_chunks": total_chunks}, f)

    # Write chunk
    chunk_path = chunk_dir / f"chunk_{chunk_index}"
    with open(chunk_path, 'wb') as f:
        f.write(contents)

    return {"upload_id": upload_id, "received": chunk_index, "total": total_chunks}

@router.post("/extract-archive")
async def extract_archive(
    upload_id: str = Form(...),
    current_user: User = Depends(require_admin_mode)
):
    """Reassemble chunks and extract files from the archive.

    Extracted media files are stored on disk and only metadata is returned.
    Use GET /archive-file/{upload_id}/{file_id} to fetch individual files.
    """
    import mimetypes
    import re
    import tarfile
    import zipfile

    # Validate upload_id
    if not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    chunk_dir = ARCHIVE_CHUNKS_DIR / upload_id
    if not chunk_dir.exists():
        raise HTTPException(status_code=400, detail="No chunks found for this upload_id")

    meta_path = chunk_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=400, detail="Missing upload metadata")

    import json as _json
    with open(meta_path, 'r') as f:
        meta = _json.load(f)

    filename = meta["filename"]
    total_chunks = meta["total_chunks"]

    # Verify all chunks are present
    for i in range(total_chunks):
        if not (chunk_dir / f"chunk_{i}").exists():
            raise HTTPException(status_code=400, detail=f"Missing chunk {i}")

    file_list = []

    try:
        # Use the chunk_dir itself for extraction (persistent, not a tempdir)
        extract_dir = chunk_dir / "extracted"
        extract_dir.mkdir(exist_ok=True)

        archive_path = chunk_dir / filename

        # Reassemble chunks into the archive file
        with open(archive_path, 'wb') as f:
            for i in range(total_chunks):
                chunk_path = chunk_dir / f"chunk_{i}"
                with open(chunk_path, 'rb') as chunk_f:
                    shutil.copyfileobj(chunk_f, f)

        # Delete chunk files now that we have the assembled archive
        for i in range(total_chunks):
            (chunk_dir / f"chunk_{i}").unlink(missing_ok=True)

        # Extract based on file type
        if filename.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    if member.startswith('/') or '..' in member:
                        raise HTTPException(status_code=400, detail="Invalid file path in archive")
                zip_ref.extractall(extract_dir)

        elif filename.endswith(('.tar.gz', '.tgz')):
            with tarfile.open(archive_path, 'r:gz') as tar_ref:
                for member in tar_ref.getmembers():
                    if member.name.startswith('/') or '..' in member.name:
                        raise HTTPException(status_code=400, detail="Invalid file path in archive")
                tar_ref.extractall(extract_dir)
        else:
            raise HTTPException(status_code=400, detail="Unsupported archive format")

        # Delete the reassembled archive to free disk space
        archive_path.unlink(missing_ok=True)

        # Collect metadata for valid extracted files
        from ...utils.format_registry import format_registry, FormatCategory
        valid_types = set(
            format_registry.get_supported_mime_types(FormatCategory.IMAGE)
            + format_registry.get_supported_mime_types(FormatCategory.VIDEO)
        )
        file_index = 0
        raw_extracted_files = [p for p in extract_dir.rglob('*') if p.is_file() and not p.is_symlink()]

        for extracted_file in raw_extracted_files:
            if not extracted_file.exists():
                continue

            mime_type, _ = mimetypes.guess_type(extracted_file.name)
            fmt = format_registry.get_format(extracted_file.name)
            if mime_type in valid_types or (fmt and fmt.category in (FormatCategory.IMAGE, FormatCategory.VIDEO)):
                if not mime_type and fmt:
                    mime_type = fmt.mime_type
                original_name = extracted_file.name
                rel_path = str(extracted_file.relative_to(extract_dir)).replace("\\", "/")
                ext = extracted_file.suffix
                media_name_lower = extracted_file.name.lower()
                media_stem_lower = extracted_file.stem.lower()

                # Check for sibling sidecar in the nested directory BEFORE moving/renaming
                sidecar_file_id = None
                sidecar_filename = None

                parent_dir = extracted_file.parent
                found_sidecar: Optional[Path] = None
                siblings = [s for s in parent_dir.iterdir() if s.is_file() and s != extracted_file]

                # Exact match with extension (e.g. image.png.json, image.png.xmp)
                for s in siblings:
                    s_name = s.name.lower()
                    if s_name == f"{media_name_lower}.json" or s_name == f"{media_name_lower}.xmp":
                        found_sidecar = s
                        break

                # Stem match without extension (e.g. image.json, image.xmp)
                if not found_sidecar:
                    for s in siblings:
                        s_name = s.name.lower()
                        if s_name == f"{media_stem_lower}.json" or s_name == f"{media_stem_lower}.xmp":
                            found_sidecar = s
                            break

                if found_sidecar and found_sidecar.exists():
                    sidecar_ext = found_sidecar.suffix
                    sidecar_target = extract_dir / f"{file_index}_sidecar{sidecar_ext}"
                    sidecar_filename = found_sidecar.name
                    sidecar_file_id = f"{file_index}_sidecar"
                    found_sidecar.rename(sidecar_target)

                # Rename to a predictable indexed name for serving
                indexed_name = f"{file_index}{ext}"
                target = extract_dir / indexed_name
                if extracted_file != target:
                    extracted_file.rename(target)

                file_info = {
                    'file_id': file_index,
                    'filename': original_name,
                    'path': rel_path,
                    'mime_type': mime_type,
                    'url': f"/api/media/archive-file/{upload_id}/{file_index}",
                }
                if sidecar_file_id:
                    file_info['sidecar_file_id'] = sidecar_file_id
                    file_info['sidecar_filename'] = sidecar_filename
                    file_info['sidecar_url'] = f"/api/media/archive-file/{upload_id}/{sidecar_file_id}"

                file_list.append(file_info)
                file_index += 1

        # Update metadata so cleanup knows this is an extracted session
        with open(meta_path, 'w') as f:
            _json.dump({"filename": filename, "total_chunks": total_chunks, "extracted": True, "file_count": file_index}, f)

        return {
            'upload_id': upload_id,
            'files': file_list,
            'count': len(file_list)
        }

    except zipfile.BadZipFile:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Invalid or corrupted zip file")
    except tarfile.TarError:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Invalid or corrupted tar.gz file")
    except HTTPException:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        logger.exception("Import error occurred")
        raise HTTPException(status_code=400, detail=safe_error_detail("Error extracting archive", e))

@router.get("/archive-file/{upload_id}/{file_id}")
async def get_archive_file(
    upload_id: str,
    file_id: str,
    current_user: User = Depends(require_admin_mode)
):
    """Serve an individual extracted file or sidecar from an archive session."""
    import re

    if not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    if not re.match(r'^\d+(_sidecar)?$', file_id):
        raise HTTPException(status_code=400, detail="Invalid file_id")

    extract_dir = ARCHIVE_CHUNKS_DIR / upload_id / "extracted"
    if not extract_dir.exists():
        raise HTTPException(status_code=404, detail="No extracted files found")

    # Find the file by index/id (could have various extensions)
    if file_id.endswith("_sidecar"):
        matches = list(extract_dir.glob(f"{file_id}.*"))
    else:
        matches = [p for p in extract_dir.glob(f"{file_id}.*") if "_sidecar" not in p.stem]

    if not matches:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = matches[0]
    import mimetypes
    mime_type, _ = mimetypes.guess_type(file_path.name)

    return FileResponse(file_path, media_type=mime_type)

@router.delete("/archive-cleanup/{upload_id}")
async def cleanup_archive(
    upload_id: str,
    current_user: User = Depends(require_admin_mode)
):
    """Clean up extracted archive files after the frontend is done with them."""
    import re

    if not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    chunk_dir = ARCHIVE_CHUNKS_DIR / upload_id
    shutil.rmtree(chunk_dir, ignore_errors=True)
    return {"message": "Cleaned up"}

MEDIA_CHUNKS_DIR = settings.CACHE_DIR / "media-chunks"
MEDIA_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

def cleanup_media_chunks(max_age_seconds: int = 0):
    """Remove leftover media-chunk directories.

    Args:
        max_age_seconds: Only remove directories older than this many seconds.
                         0 means remove everything (used on startup).
    """
    import time

    if not MEDIA_CHUNKS_DIR.exists():
        return

    now = time.time()
    for child in MEDIA_CHUNKS_DIR.iterdir():
        if child.is_dir():
            if max_age_seconds > 0:
                try:
                    age = now - child.stat().st_mtime
                    if age < max_age_seconds:
                        continue
                except OSError:
                    pass
            shutil.rmtree(child, ignore_errors=True)

@router.post("/upload-chunk")
async def upload_media_chunk(
    file: UploadFile = File(...),
    upload_id: Optional[str] = Form(None),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
    current_user: User = Depends(require_admin_mode)
):
    """Receive a single chunk of a media upload."""
    import re

    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=400, detail="Invalid chunk_index")

    if chunk_index == 0 and not upload_id:
        upload_id = str(uuid.uuid4())
    elif not upload_id or not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid or missing upload_id")

    contents = await file.read()
    if len(contents) > MAX_CHUNK_SIZE:
        raise HTTPException(status_code=400, detail=f"Chunk too large (max {MAX_CHUNK_SIZE // (1024 * 1024)}MB)")

    chunk_dir = MEDIA_CHUNKS_DIR / upload_id
    chunk_dir.mkdir(parents=True, exist_ok=True)

    meta_path = chunk_dir / "meta.json"
    if chunk_index == 0:
        import json as _json
        with open(meta_path, 'w') as f:
            _json.dump({"filename": filename, "total_chunks": total_chunks}, f)

    chunk_path = chunk_dir / f"chunk_{chunk_index}"
    with open(chunk_path, 'wb') as f:
        f.write(contents)

    return {"upload_id": upload_id, "received": chunk_index, "total": total_chunks}

@router.post("/upload-finalize", response_model=MediaResponse)
async def finalize_chunked_upload(
    upload_id: str = Form(...),
    rating: RatingEnum = Form(RatingEnum.safe),
    tags: str = Form(""),
    album_ids: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    category_hints: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    custom_date: Optional[str] = Form(None),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Reassemble chunks and process as a regular media upload."""
    import re
    import json as _json

    if not re.match(r'^[0-9a-f\-]{36}$', upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    chunk_dir = MEDIA_CHUNKS_DIR / upload_id
    if not chunk_dir.exists():
        raise HTTPException(status_code=400, detail="No chunks found for this upload_id")

    meta_path = chunk_dir / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=400, detail="Missing upload metadata")

    with open(meta_path) as f:
        meta = _json.load(f)

    filename = meta["filename"]
    total_chunks = meta["total_chunks"]

    for i in range(total_chunks):
        if not (chunk_dir / f"chunk_{i}").exists():
            raise HTTPException(status_code=400, detail=f"Missing chunk {i}")

    # Reassemble into a single file in ORIGINAL_DIR
    try:
        unique_filename = get_unique_filename(settings.ORIGINAL_DIR, filename)
        file_path = settings.ORIGINAL_DIR / unique_filename

        with open(file_path, 'wb') as out_f:
            for i in range(total_chunks):
                chunk_path = chunk_dir / f"chunk_{i}"
                with open(chunk_path, 'rb') as chunk_f:
                    shutil.copyfileobj(chunk_f, out_f)

        # Clean up chunks immediately
        shutil.rmtree(chunk_dir, ignore_errors=True)

        # Delegate to shared helper
        try:
            return process_and_save_media(
                db=db,
                file_path=file_path,
                unique_filename=unique_filename,
                rating=rating,
                tags=tags,
                album_ids=album_ids,
                source=source,
                category_hints=category_hints,
                description=description,
                explicit_date=custom_date,
            )
        except HTTPException as e:
            file_path.unlink(missing_ok=True)
            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chunked upload finalize: {e}", exc_info=True)

        if 'file_path' in locals() and file_path.exists():
            file_path.unlink(missing_ok=True)

        shutil.rmtree(chunk_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=safe_error_detail("Chunked upload failed", e))
