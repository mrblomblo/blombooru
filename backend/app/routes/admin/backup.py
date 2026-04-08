import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...auth import get_current_admin_user, require_admin_mode
from ...config import APP_VERSION, SCHEMA_VERSION, settings
from ...utils.request_helpers import safe_error_detail
from ...database import get_db
from ...models import User
from ...utils.backup import (generate_tags_csv_stream, generate_tags_dump,
                             get_media_files_generator, import_full_backup,
                             stream_zip_generator)
from ...utils.logger import logger

router = APIRouter()

@router.get("/backup/tags")
async def backup_tags(
    current_user: User = Depends(get_current_admin_user)
):
    """Export all tags and aliases as a CSV file compatible with the import format."""
    from ...database import SessionLocal
    
    def csv_generator():
        db = SessionLocal()
        try:
            csv_stream = generate_tags_csv_stream(db)
            yield from csv_stream
        finally:
            db.close()
            
    return StreamingResponse(
        csv_generator(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=blombooru_tags.csv"}
    )

@router.get("/backup/media")
async def backup_media(
    current_user: User = Depends(get_current_admin_user),
):
    """Download a ZIP backup of all media files"""
    files_gen = get_media_files_generator()
    zip_stream = stream_zip_generator(files_gen)
    
    return StreamingResponse(
        zip_stream,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=blombooru_media_backup.zip"}
    )

@router.get("/backup/full")
async def backup_full_db(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Download a full backup (Media + Database JSON)"""
    
    dump_data = generate_tags_dump(db)
    
    from sqlalchemy.orm import selectinload

    from ...models import Album, Media

    album_list = []
    media_list = []
    albums_query = db.query(Album).all()
    
    for album in albums_query:
        media_hashes = [m.hash for m in album.media]
        child_ids = [child.id for child in album.children]
        
        album_list.append({
            "id": album.id,
            "name": album.name,
            "created_at": album.created_at.isoformat() if album.created_at else None,
            "last_modified": album.last_modified.isoformat() if album.last_modified else None,
            "media_hashes": media_hashes,
            "child_ids": child_ids
        })
    
    media_query = db.query(Media).options(selectinload(Media.parent)).all()
    
    for m in media_query:
        try:
            media_path = Path(m.path)
            if settings.ORIGINAL_DIR in media_path.parents or str(settings.ORIGINAL_DIR) in str(media_path):
                try:
                    rel_path = media_path.relative_to(settings.ORIGINAL_DIR)
                    archive_path = f"media/{rel_path}"
                except ValueError:
                    archive_path = f"media/{m.filename}"
            else:
                archive_path = f"media/{m.filename}"
        except Exception as e:
            logger.warning(f"Warning: Could not construct archive path for {m.filename}: {e}")
            archive_path = f"media/{m.filename}"
        
        media_list.append({
            "filename": m.filename,
            "hash": m.hash,
            "file_type": m.file_type.value,
            "mime_type": m.mime_type,
            "file_size": m.file_size,
            "width": m.width,
            "height": m.height,
            "duration": m.duration,
            "rating": m.rating.value if m.rating else 'safe',
            "tags": [t.name for t in m.tags],
            "archive_path": archive_path,
            "parent_hash": m.parent.hash if m.parent else None
        })
        
    backup_metadata = {
        "version": APP_VERSION,
        "schema_version": SCHEMA_VERSION,
        "type": "full_backup",
        "media": media_list,
        "albums": album_list
    }
    
    def mixed_generator():
        from ...database import SessionLocal
        stream_db = SessionLocal()
        tmp_csv_path = None
        tmp_json_path = None
        
        try:
            logger.info("Starting full backup generation...")
            
            logger.debug("Generating tags.csv...")
            try:
                with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as tmp_csv:
                    csv_gen = generate_tags_csv_stream(stream_db)
                    for chunk in csv_gen:
                        tmp_csv.write(chunk)
                    tmp_csv_path = Path(tmp_csv.name)
                logger.debug(f"tags.csv generated: {tmp_csv_path}")
            except Exception as e:
                logger.error(f"Error generating tags.csv: {e}", exc_info=True)
                raise
                
            logger.debug("Generating backup.json...")
            try:
                with tempfile.NamedTemporaryFile(delete=False, mode='wb') as tmp_json:
                    tmp_json.write(json.dumps(backup_metadata, indent=2).encode('utf-8'))
                    tmp_json_path = Path(tmp_json.name)
                logger.debug(f"backup.json generated: {tmp_json_path}")
            except Exception as e:
                logger.error(f"Error generating backup.json: {e}", exc_info=True)
                raise
                
            try:
                logger.debug("Yielding tags.csv to ZIP stream...")
                yield ("tags.csv", tmp_csv_path)
                
                logger.debug("Yielding backup.json to ZIP stream...")
                yield ("backup.json", tmp_json_path)
                
                logger.debug("Yielding media files to ZIP stream...")
                media_gen = get_media_files_generator()
                file_count = 0
                for item in media_gen:
                    yield item
                    file_count += 1
                    if file_count % 100 == 0:
                        logger.debug(f"Processed {file_count} media files...")
                logger.info(f"All {file_count} media files yielded to ZIP stream")
                
            except Exception as e:
                logger.error(f"Error during ZIP streaming: {e}", exc_info=True)
                raise
            finally:
                if tmp_csv_path and tmp_csv_path.exists():
                    try:
                        os.unlink(tmp_csv_path)
                        logger.debug("Cleaned up tags.csv temp file")
                    except Exception as e:
                        logger.error(f"Error cleaning up tags.csv: {e}")
                        
                if tmp_json_path and tmp_json_path.exists():
                    try:
                        os.unlink(tmp_json_path)
                        logger.debug("Cleaned up backup.json temp file")
                    except Exception as e:
                        logger.error(f"Error cleaning up backup.json: {e}")
        except Exception as e:
            logger.error(f"Fatal error in mixed_generator: {e}", exc_info=True)
            raise
        finally:
            stream_db.close()
            logger.info("Backup generation complete, database session closed")
                
    zip_stream = stream_zip_generator(mixed_generator())
    
    return StreamingResponse(
        zip_stream,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=blombooru_full_backup.zip"}
    )

@router.post("/import/full")
async def import_full(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Import a full backup ZIP"""
    try:
        result = import_full_backup(file.file, db)
        return result
    except Exception as e:
        logger.exception("Import error occurred")
        raise HTTPException(status_code=400, detail=safe_error_detail("Import failed", e))
