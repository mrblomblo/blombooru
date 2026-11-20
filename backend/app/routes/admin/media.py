import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from ...auth import require_admin_mode
from ...config import settings
from ...database import get_db
from ...models import Media, User
from ...services.maintenance_jobs import maintenance_jobs
from ...utils.file_scanner import find_untracked_media, relink_media_files
from ...utils.logger import logger
from ...utils.thumbnail_generator import generate_thumbnail, THUMBNAIL_EXT
from sqlalchemy.orm import Session

router = APIRouter()

_maintenance_lock = threading.Lock()

async def _run_exclusive(fn, *args):
    """Run a blocking maintenance job in the threadpool, rejecting it if another is running."""
    if not _maintenance_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="common.processing")

    def runner():
        try:
            return fn(*args)
        finally:
            _maintenance_lock.release()

    return await run_in_threadpool(runner)

@router.post("/scan-media")
async def scan_media(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Find untracked media files"""    
    result = find_untracked_media(db)
    
    return {
        'new_files': result['new_files'],
        'files': [f['path'] for f in result['files']]
    }

@router.get("/get-untracked-file-info")
async def get_untracked_file_info(
    path: str,
    current_user: User = Depends(require_admin_mode)
):
    """Return metadata (name, size, mime_type) for an untracked file without serving its bytes."""
    import mimetypes
    
    file_path = Path(path)
    
    if not file_path.is_absolute():
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    try:
        file_path = file_path.resolve()
        if not file_path.is_relative_to(settings.ORIGINAL_DIR.resolve()):
            raise ValueError()
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        mime_type = "application/octet-stream"
    
    stat = file_path.stat()
    
    return {
        "name": file_path.name,
        "size": stat.st_size,
        "mime_type": mime_type,
    }

@router.get("/get-untracked-file")
async def get_untracked_file(
    path: str,
    current_user: User = Depends(require_admin_mode)
):
    """Serve an untracked file for importing. Used for direct preview usage."""
    import mimetypes
    
    from fastapi.responses import FileResponse
    
    file_path = Path(path)
    
    if not file_path.is_absolute():
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    try:
        file_path = file_path.resolve()
        if not file_path.is_relative_to(settings.ORIGINAL_DIR.resolve()):
            raise ValueError()
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        mime_type = "application/octet-stream"
    
    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        filename=file_path.name
    )

@router.get("/media-stats")
async def get_media_stats(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Get media statistics"""
    from sqlalchemy import func

    from ...models import Media
    
    total_media = db.query(Media).count()
    total_images = db.query(Media).filter(Media.file_type == 'image').count()
    total_gifs = db.query(Media).filter(Media.file_type == 'gif').count()
    total_videos = db.query(Media).filter(Media.file_type == 'video').count()
    
    return {
        "total_media": total_media,
        "total_images": total_images,
        "total_gifs": total_gifs,
        "total_videos": total_videos,
    }

@router.get("/stats")
async def get_comprehensive_stats(
    current_user: User = Depends(require_admin_mode),
    db: Session = Depends(get_db)
):
    """Get comprehensive statistics for admin dashboard"""
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from ...models import Album, Media, Tag, TagAlias

    total_media = db.query(Media).count()
    media_by_type = {
        'image': db.query(Media).filter(Media.file_type == 'image').count(),
        'gif': db.query(Media).filter(Media.file_type == 'gif').count(),
        'video': db.query(Media).filter(Media.file_type == 'video').count()
    }
    
    media_by_rating = {
        'safe': db.query(Media).filter(Media.rating == 'safe').count(),
        'questionable': db.query(Media).filter(Media.rating == 'questionable').count(),
        'explicit': db.query(Media).filter(Media.rating == 'explicit').count()
    }
    
    today = datetime.now().date()
    start_date = today - timedelta(days=29)
    start_datetime = datetime.combine(start_date, datetime.min.time())
    
    upload_trends = db.query(
        func.date(Media.uploaded_at).label('date'),
        func.count(Media.id).label('count')
    ).filter(
        Media.uploaded_at >= start_datetime
    ).group_by(
        func.date(Media.uploaded_at)
    ).order_by('date').all()
    
    counts_by_date = {str(trend.date): trend.count for trend in upload_trends}
    upload_trends_data = [
        {
            'date': (start_date + timedelta(days=i)).isoformat(),
            'count': counts_by_date.get((start_date + timedelta(days=i)).isoformat(), 0)
        }
        for i in range(30)
    ]
    
    total_tags = db.query(Tag).count()
    total_aliases = db.query(TagAlias).count()
    
    top_tags = db.query(Tag).order_by(Tag.post_count.desc()).limit(10).all()
    top_tags_data = [
        {'name': tag.name, 'count': tag.post_count, 'category': tag.category.value}
        for tag in top_tags
    ]
    
    from ...models import TagCategoryEnum
    top_tags_by_category = {}
    for category in TagCategoryEnum:
        category_tags = db.query(Tag).filter(
            Tag.category == category
        ).order_by(Tag.post_count.desc()).limit(10).all()
        
        top_tags_by_category[category.value] = [
            {'name': tag.name, 'count': tag.post_count}
            for tag in category_tags
        ]
    
    tag_categories = db.query(
        Tag.category,
        func.count(Tag.id).label('count')
    ).group_by(Tag.category).all()
    
    tag_category_data = {
        cat.category.value: cat.count
        for cat in tag_categories
    }
    
    total_albums = db.query(Album).count()
    
    from sqlalchemy import func as sql_func

    album_media_counts = db.query(
        Album.id,
        sql_func.count(Media.id).label('media_count')
    ).outerjoin(
        Album.media
    ).group_by(Album.id).all()
    
    album_size_distribution = {
        '0': 0,
        '1-10': 0,
        '11-50': 0,
        '51-100': 0,
        '100+': 0
    }
    
    for album_id, count in album_media_counts:
        if count == 0:
            album_size_distribution['0'] += 1
        elif count <= 10:
            album_size_distribution['1-10'] += 1
        elif count <= 50:
            album_size_distribution['11-50'] += 1
        elif count <= 100:
            album_size_distribution['51-100'] += 1
        else:
            album_size_distribution['100+'] += 1
    
    storage_stats = db.query(
        func.sum(Media.file_size).label('total_size'),
        func.avg(Media.file_size).label('avg_size')
    ).first()
    
    total_storage = storage_stats.total_size or 0
    avg_file_size = int(storage_stats.avg_size or 0)
    
    from sqlalchemy import exists
    from sqlalchemy.orm import aliased
    
    ChildMedia = aliased(Media)
    
    total_parents = db.query(Media).filter(
        exists().where(ChildMedia.parent_id == Media.id)
    ).count()
    
    total_children = db.query(Media).filter(Media.parent_id != None).count()

    return {
        "media": {
            "total": total_media,
            "by_type": media_by_type,
            "by_rating": media_by_rating,
            "relationships": {
                "total_parents": total_parents,
                "total_children": total_children
            }
        },
        "upload_trends": upload_trends_data,
        "tags": {
            "total": total_tags,
            "total_aliases": total_aliases,
            "total_with_aliases": total_tags + total_aliases,
            "top_tags": top_tags_data,
            "top_tags_by_category": top_tags_by_category,
            "by_category": tag_category_data
        },
        "albums": {
            "total": total_albums,
            "size_distribution": album_size_distribution
        },
        "storage": {
            "total_bytes": total_storage,
            "avg_file_size_bytes": avg_file_size
        }
    }

def _do_regenerate_all_thumbnails(progress_cb=None) -> dict:
    """Synchronous worker for regenerating all thumbnails."""
    from ...database import SessionLocal

    thumbnail_dir = settings.THUMBNAIL_DIR
    base_dir = settings.BASE_DIR

    # Delete all existing thumbnails
    deleted = 0
    if thumbnail_dir.exists():
        for f in thumbnail_dir.rglob("*"):
            if f.is_file():
                try:
                    f.unlink()
                    deleted += 1
                except Exception as e:
                    logger.error(f"Error deleting thumbnail {f}: {e}")

    db = SessionLocal()
    try:
        # Re-generate thumbnails for all media items
        all_media = db.query(Media).all()
        total = len(all_media)
        generated = 0
        failed = 0

        if progress_cb:
            progress_cb(
                current=0,
                total=total,
                deleted=deleted,
                generated=0,
                failed=0,
                current_file=None,
            )

        for idx, item in enumerate(all_media):
            if progress_cb:
                progress_cb(current=idx + 1, current_file=item.filename)

            # Paths in DB are relative to BASE_DIR
            source_path = base_dir / item.path

            if not source_path.exists():
                logger.warning(f"Source file missing for media {item.id}: {source_path}")
                failed += 1
                if progress_cb:
                    progress_cb(failed=failed)
                continue

            thumbnail_filename = f"{item.hash}{THUMBNAIL_EXT}"
            thumbnail_path = thumbnail_dir / thumbnail_filename

            try:
                ok = generate_thumbnail(source_path, thumbnail_path, item.file_type)
                if ok:
                    item.thumbnail_path = str(thumbnail_path.relative_to(base_dir))
                    generated += 1
                else:
                    item.thumbnail_path = None
                    failed += 1
            except Exception as e:
                logger.error(f"Error regenerating thumbnail for media {item.id}: {e}", exc_info=True)
                item.thumbnail_path = None
                failed += 1

            if progress_cb:
                progress_cb(generated=generated, failed=failed)

        db.commit()

        return {
            "deleted": deleted,
            "generated": generated,
            "failed": failed,
            "total": total,
        }
    finally:
        db.close()

def _do_generate_missing_thumbnails(progress_cb=None) -> dict:
    """Synchronous worker for generating missing thumbnails only."""
    from ...database import SessionLocal

    thumbnail_dir = settings.THUMBNAIL_DIR
    base_dir = settings.BASE_DIR

    db = SessionLocal()
    try:
        # Collect all thumbnail paths registered in the DB (resolved to absolute)
        all_media = db.query(Media).all()
        total = len(all_media)
        registered_paths: set = set()
        for item in all_media:
            if item.thumbnail_path:
                # Paths in DB are relative to BASE_DIR
                registered_paths.add(str((base_dir / item.thumbnail_path).resolve()))

        # Delete orphaned thumbnail files (files with no registered DB path)
        orphans_deleted = 0
        if thumbnail_dir.exists():
            for f in thumbnail_dir.rglob("*"):
                if f.is_file() and str(f.resolve()) not in registered_paths:
                    try:
                        f.unlink()
                        orphans_deleted += 1
                    except Exception as e:
                        logger.error(f"Error deleting orphaned thumbnail {f}: {e}")

        # Generate thumbnails for media items whose thumbnail file is missing
        generated = 0
        failed = 0
        skipped = 0

        if progress_cb:
            progress_cb(
                current=0,
                total=total,
                orphans_deleted=orphans_deleted,
                generated=0,
                failed=0,
                skipped=0,
                current_file=None,
            )

        for idx, item in enumerate(all_media):
            if progress_cb:
                progress_cb(current=idx + 1, current_file=item.filename)

            # Check whether the recorded thumbnail file actually exists
            thumb_exists = (
                item.thumbnail_path is not None
                and (base_dir / item.thumbnail_path).exists()
            )
            if thumb_exists:
                skipped += 1
                if progress_cb:
                    progress_cb(skipped=skipped)
                continue

            # Source path is relative to BASE_DIR
            source_path = base_dir / item.path

            if not source_path.exists():
                logger.warning(f"Source file missing for media {item.id}: {source_path}")
                failed += 1
                if progress_cb:
                    progress_cb(failed=failed)
                continue

            thumbnail_filename = f"{item.hash}{THUMBNAIL_EXT}"
            thumbnail_path = thumbnail_dir / thumbnail_filename

            try:
                ok = generate_thumbnail(source_path, thumbnail_path, item.file_type)
                if ok:
                    item.thumbnail_path = str(thumbnail_path.relative_to(base_dir))
                    generated += 1
                else:
                    item.thumbnail_path = None
                    failed += 1
            except Exception as e:
                logger.error(f"Error generating thumbnail for media {item.id}: {e}", exc_info=True)
                item.thumbnail_path = None
                failed += 1

            if progress_cb:
                progress_cb(generated=generated, failed=failed)

        db.commit()

        return {
            "orphans_deleted": orphans_deleted,
            "generated": generated,
            "failed": failed,
            "skipped": skipped,
            "total": total,
        }
    finally:
        db.close()

@router.post("/regenerate-all-thumbnails")
async def regenerate_all_thumbnails(
    background: bool = False,
    current_user: User = Depends(require_admin_mode),
):
    """Delete all thumbnails and regenerate them from source files, updating DB paths."""
    if background:
        started, status = maintenance_jobs.start_job(
            "regenerate_all_thumbnails",
            _do_regenerate_all_thumbnails,
            execution_lock=_maintenance_lock,
            initial_fields={"deleted": 0, "generated": 0, "failed": 0},
        )
        return {"status": "started" if started else "already_running", "job": status}

    try:
        result = await _run_exclusive(_do_regenerate_all_thumbnails)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating all thumbnails: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-missing-thumbnails")
async def generate_missing_thumbnails(
    background: bool = False,
    current_user: User = Depends(require_admin_mode),
):
    """Remove orphaned thumbnail files and generate thumbnails for media items that are missing one."""
    if background:
        started, status = maintenance_jobs.start_job(
            "generate_missing_thumbnails",
            _do_generate_missing_thumbnails,
            execution_lock=_maintenance_lock,
            initial_fields={"orphans_deleted": 0, "generated": 0, "failed": 0, "skipped": 0},
        )
        return {"status": "started" if started else "already_running", "job": status}

    try:
        result = await _run_exclusive(_do_generate_missing_thumbnails)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating missing thumbnails: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/relink-media")
async def relink_media(
    background: bool = False,
    current_user: User = Depends(require_admin_mode),
):
    """Scan storage and re-link database records for moved or renamed media files based on content hash."""
    if background:
        started, status = maintenance_jobs.start_job(
            "relink_media",
            lambda cb: relink_media_files(progress_cb=cb),
            execution_lock=_maintenance_lock,
            initial_fields={"relinked": 0, "unresolved": 0},
        )
        return {"status": "started" if started else "already_running", "job": status}

    try:
        result = await _run_exclusive(relink_media_files)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error relinking media: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

_transcode_status = {
    "running": False,
    "current": 0,
    "total": 0,
    "transcoded": 0,
    "already_transcoded": 0,
    "skipped": 0,
    "failed": 0,
    "current_file": None,
    "error": None,
    "last_result": None,
}

def _do_transcode_incompatible_media() -> dict:
    """Worker for transcoding incompatible media files in the library with progressive commits."""
    global _transcode_status
    from ...database import SessionLocal
    from ...utils.transcoder import (
        is_transcoding_required,
        transcode_media_if_needed,
    )

    base_dir = settings.BASE_DIR

    db = SessionLocal()
    try:
        all_media = db.query(Media).all()
        total_items = len(all_media)
        transcoded_count = 0
        already_ok_count = 0
        skipped_count = 0
        failed_count = 0

        _transcode_status["total"] = total_items

        for idx, item in enumerate(all_media):
            _transcode_status["current"] = idx + 1
            _transcode_status["current_file"] = item.filename

            source_path = base_dir / item.path
            if not source_path.exists() or not source_path.is_file():
                skipped_count += 1
                _transcode_status["skipped"] = skipped_count
                continue

            # If item already has a valid transcoded file on disk, verify it exists
            if item.transcoded_path:
                transc_abs = base_dir / item.transcoded_path
                if transc_abs.exists() and transc_abs.is_file() and transc_abs.stat().st_size > 0:
                    already_ok_count += 1
                    _transcode_status["already_transcoded"] = already_ok_count
                    continue

            # Check if transcoding is required
            req = is_transcoding_required(source_path)
            if req is True:
                trans_dest = transcode_media_if_needed(source_path)
                if trans_dest and trans_dest.exists() and trans_dest.stat().st_size > 0:
                    item.transcoded_path = str(trans_dest.relative_to(base_dir))
                    transcoded_count += 1
                    _transcode_status["transcoded"] = transcoded_count
                    # Progressive commit: save immediately on each transcode
                    db.commit()
                else:
                    failed_count += 1
                    _transcode_status["failed"] = failed_count
            elif req is False:
                skipped_count += 1
                _transcode_status["skipped"] = skipped_count
            else:
                # Probe error or unknown
                failed_count += 1
                _transcode_status["failed"] = failed_count

            # Periodic commit every 50 items
            if (idx + 1) % 50 == 0:
                db.commit()

        db.commit()

        result = {
            "transcoded": transcoded_count,
            "already_transcoded": already_ok_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "total": total_items,
        }
        _transcode_status["last_result"] = result
        return result
    except Exception as e:
        _transcode_status["error"] = str(e)
        raise
    finally:
        _transcode_status["running"] = False
        _transcode_status["current_file"] = None
        db.close()

@router.post("/transcode-media")
async def transcode_media(
    current_user: User = Depends(require_admin_mode),
):
    """Start background library transcoding for incompatible codecs/containers."""
    if not _maintenance_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="common.processing")

    _transcode_status.update({
        "running": True,
        "current": 0,
        "total": 0,
        "transcoded": 0,
        "already_transcoded": 0,
        "skipped": 0,
        "failed": 0,
        "current_file": None,
        "error": None,
        "last_result": None,
    })

    def worker():
        try:
            _do_transcode_incompatible_media()
        except Exception as e:
            logger.error(f"Error in background transcoding maintenance: {e}", exc_info=True)
        finally:
            _transcode_status["running"] = False
            _maintenance_lock.release()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    return {"status": "started", "message": "Transcoding job started in background"}

@router.get("/transcode-media/status")
async def get_transcode_media_status(
    current_user: User = Depends(require_admin_mode),
):
    """Get the current progress status of background library transcoding."""
    return dict(_transcode_status)
