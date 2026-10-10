import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload

from ...auth import require_admin_mode
from ...config import APP_VERSION, SCHEMA_VERSION, settings
from ...custom_themes import custom_theme_manager
from ...database import get_db
from ...models import (Album, BooruConfig, Media, TagImplication, User,
                      blombooru_album_hierarchy, blombooru_album_media)
from ...utils.backup import (generate_tags_csv_stream,
                             get_custom_theme_files_generator,
                             get_media_files_generator, import_full_backup,
                             stream_zip_generator)
from ...utils.logger import logger
from ...utils.request_helpers import safe_error_detail

router = APIRouter()

@router.get("/backup/tags")
async def backup_tags(
    current_user: User = Depends(require_admin_mode)
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
            
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return StreamingResponse(
        csv_generator(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=blombooru_tags-{timestamp}.csv"}
    )

@router.get("/backup/media")
async def backup_media(
    current_user: User = Depends(require_admin_mode),
):
    """Download a ZIP backup of all media files"""
    files_gen = get_media_files_generator()
    zip_stream = stream_zip_generator(files_gen)
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return StreamingResponse(
        zip_stream,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=blombooru_media_backup-{timestamp}.zip"}
    )

@router.get("/backup/full")
async def backup_full_db(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Download a full backup (Media + Custom Themes + Database JSON + Tags CSV)"""

    # 1. Albums export
    album_list = []
    albums_query = db.query(Album).all()
    
    for album in albums_query:
        # Fetch album media with metadata
        album_media_rows = (
            db.query(blombooru_album_media.c.added_at, blombooru_album_media.c.sort_position, Media.hash)
            .join(Media, blombooru_album_media.c.media_id == Media.id)
            .filter(blombooru_album_media.c.album_id == album.id)
            .all()
        )

        media_items = [
            {
                "hash": row.hash,
                "added_at": row.added_at.isoformat() if row.added_at else None,
                "sort_position": row.sort_position
            }
            for row in album_media_rows
        ]
        media_hashes = [row.hash for row in album_media_rows]

        # Fetch album children with sort_position
        child_rows = (
            db.query(blombooru_album_hierarchy.c.child_album_id, blombooru_album_hierarchy.c.sort_position)
            .filter(blombooru_album_hierarchy.c.parent_album_id == album.id)
            .all()
        )
        child_items = [
            {
                "id": row.child_album_id,
                "sort_position": row.sort_position
            }
            for row in child_rows
        ]
        child_ids = [row.child_album_id for row in child_rows]
        
        album_list.append({
            "id": album.id,
            "name": album.name,
            "sort_position": album.sort_position,
            "created_at": album.created_at.isoformat() if album.created_at else None,
            "updated_at": album.updated_at.isoformat() if album.updated_at else None,
            "last_modified": album.last_modified.isoformat() if album.last_modified else None,
            "media": media_items,
            "media_hashes": media_hashes,
            "child_ids": child_ids,
            "children": child_items
        })
    
    # 2. Media export
    media_list = []
    media_query = (
        db.query(Media)
        .options(selectinload(Media.parent), selectinload(Media.tags))
        .all()
    )
    
    for m in media_query:
        try:
            media_path_str = m.path or ""
            if media_path_str.startswith("media/original/"):
                rel_path = media_path_str[len("media/original/"):]
            elif media_path_str.startswith("media/"):
                rel_path = media_path_str[len("media/"):]
            else:
                rel_path = m.filename
            archive_path = f"media/{rel_path}"
        except Exception as e:
            logger.warning(f"Could not construct archive path for {m.filename}: {e}")
            archive_path = f"media/{m.filename}"
        
        file_type_val = m.file_type.value if hasattr(m.file_type, 'value') else str(m.file_type)
        rating_val = m.rating.value if hasattr(m.rating, 'value') else (str(m.rating) if m.rating else 'safe')
        
        media_list.append({
            "filename": m.filename,
            "hash": m.hash,
            "file_type": file_type_val,
            "mime_type": m.mime_type,
            "file_size": m.file_size,
            "width": m.width,
            "height": m.height,
            "duration": m.duration,
            "rating": rating_val,
            "source": m.source,
            "description": m.description,
            "description_enlarged": bool(m.description_enlarged),
            "uploaded_at": m.uploaded_at.isoformat() if m.uploaded_at else None,
            "is_shared": bool(m.is_shared),
            "share_uuid": m.share_uuid,
            "share_ai_metadata": bool(m.share_ai_metadata),
            "share_language": m.share_language,
            "transcoded_path": m.transcoded_path,
            "tags": [t.name for t in m.tags],
            "archive_path": archive_path,
            "parent_hash": m.parent.hash if m.parent else None
        })
        
    # 3. Tag Implications export
    implications_list = []
    implications_query = (
        db.query(TagImplication)
        .options(selectinload(TagImplication.target_tags), selectinload(TagImplication.implied_tags))
        .all()
    )
    for imp in implications_query:
        implications_list.append({
            "target_tags": [t.name for t in imp.target_tags],
            "target_tag_patterns": imp.target_tag_patterns or [],
            "implied_tags": [t.name for t in imp.implied_tags],
            "created_at": imp.created_at.isoformat() if imp.created_at else None
        })

    # 4. Booru Config export
    booru_config_list = []
    booru_configs = db.query(BooruConfig).all()
    for cfg in booru_configs:
        booru_config_list.append({
            "domain": cfg.domain,
            "username": cfg.username,
            "api_key": cfg.api_key,
            "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
            "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None
        })

    # 5. Custom Themes metadata export
    custom_themes_list = custom_theme_manager.get_all()

    # 6. UI & Application Settings export (export all settings from settings.json, excluding sensitive host credentials)
    app_settings_export = dict(settings.settings)
    app_settings_export.update(settings.file_settings)

    # Exclude sensitive host connection parameters, secret key, and initial setup state
    app_settings_export.pop("secret_key", None)
    app_settings_export.pop("database", None)
    app_settings_export.pop("redis", None)
    app_settings_export.pop("shared_tags", None)
    app_settings_export.pop("first_run", None)

    # Attach media_hash for custom_background if set
    if "custom_background" in app_settings_export and isinstance(app_settings_export["custom_background"], dict):
        bg = dict(app_settings_export["custom_background"])
        if bg.get("media_id"):
            bg_media = db.query(Media).filter(Media.id == bg["media_id"]).first()
            if bg_media:
                bg["media_hash"] = bg_media.hash
        app_settings_export["custom_background"] = bg
        
    backup_metadata = {
        "version": APP_VERSION,
        "schema_version": SCHEMA_VERSION,
        "type": "full_backup",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "media": media_list,
        "albums": album_list,
        "tag_implications": implications_list,
        "booru_config": booru_config_list,
        "custom_themes": custom_themes_list,
        "settings": app_settings_export
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
                
                logger.debug("Yielding custom theme files to ZIP stream...")
                theme_files_gen = get_custom_theme_files_generator()
                for theme_item in theme_files_gen:
                    yield theme_item
                
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
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return StreamingResponse(
        zip_stream,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=blombooru_full_backup-{timestamp}.zip"}
    )

@router.post("/import/full")
async def import_full(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Import a full backup ZIP."""
    try:
        result = import_full_backup(file.file, db)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Import error occurred")
        raise HTTPException(status_code=400, detail=safe_error_detail("Import failed", e))
