import re
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Media
from .logger import logger
from .format_registry import format_registry, FormatCategory
from .media_processor import calculate_file_hash, get_mime_type
from .transcoder import get_transcoded_path_for_original, transcode_media_if_needed

def is_supported_file(filename: str) -> bool:
    """Check if file extension is supported for media gallery"""
    fmt = format_registry.get_format(filename)
    return fmt is not None and fmt.category in (FormatCategory.IMAGE, FormatCategory.VIDEO)

def natural_sort_key(s: str) -> list:
    """Key function for natural (human-friendly) alphanumeric sort."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

def find_untracked_media(db: Session) -> dict:
    """Find untracked media files without processing them"""
    original_dir = settings.ORIGINAL_DIR
    untracked_files = []
    
    # Get all tracked files by multiple methods:
    # 1. File hashes (primary method)
    tracked_hashes = set()
    # 2. Absolute file paths (backup method)
    tracked_paths = set()
    
    all_media = db.query(Media).all()
    
    for media in all_media:
        if media.hash:
            tracked_hashes.add(media.hash)

        if media.path:
            try:
                abs_path = (settings.BASE_DIR / media.path).resolve()
                tracked_paths.add(str(abs_path))
            except Exception:
                pass
        
        if hasattr(media, 'original_path') and media.original_path:
            try:
                abs_path = Path(media.original_path).resolve()
                tracked_paths.add(str(abs_path))
            except Exception:
                pass
    
    logger.info(f"Scanning directory: {original_dir}")
    logger.debug(f"Tracked hashes: {len(tracked_hashes)}")
    logger.debug(f"Tracked paths: {len(tracked_paths)}")
    
    for file_path in original_dir.rglob('*'):
        if file_path.is_symlink():
            continue
            
        if not file_path.is_file() or not is_supported_file(file_path.name):
            continue
        
        try:
            abs_path = str(file_path.resolve())
            
            if abs_path in tracked_paths:
                continue
            
            mime_type = get_mime_type(file_path)
            if not mime_type.startswith('image/') and not mime_type.startswith('video/') and mime_type not in ('application/x-matroska', 'application/vnd.rn-realmedia'):
                continue
            
            file_hash = calculate_file_hash(file_path)
            if file_hash in tracked_hashes:
                continue
            
            untracked_files.append({
                'path': str(file_path),
                'filename': file_path.name,
                'hash': file_hash
            })
            
        except Exception as e:
            logger.error(f"Error checking file {file_path.name}: {str(e)}")
            continue
    
    logger.debug(f"Found {len(untracked_files)} untracked files")
    
    untracked_files.sort(key=lambda x: natural_sort_key(x['path']))
    
    return {
        'new_files': len(untracked_files),
        'files': untracked_files
    }

def relink_media_files(db: Session) -> dict:
    """Scan original_dir and re-link database records for moved or renamed files based on hash."""
    from .cache import invalidate_media_cache, invalidate_media_item_cache
    from .thumbnail_generator import generate_thumbnail, THUMBNAIL_EXT

    original_dir = settings.ORIGINAL_DIR
    base_dir = settings.BASE_DIR
    thumbnail_dir = settings.THUMBNAIL_DIR

    all_media = db.query(Media).all()
    existing_tracked_paths = set()
    missing_media_by_hash = {}

    for media in all_media:
        if not media.path or not media.hash:
            continue
        try:
            abs_path = (base_dir / media.path).resolve()
            if abs_path.exists() and abs_path.is_file():
                existing_tracked_paths.add(str(abs_path))
            else:
                missing_media_by_hash[media.hash] = media
        except Exception:
            missing_media_by_hash[media.hash] = media

    if not missing_media_by_hash:
        return {
            'relinked': 0,
            'unresolved': 0,
            'total_checked': len(all_media),
            'details': []
        }

    logger.info(f"Relinking media: {len(missing_media_by_hash)} missing records to search for in {original_dir}")
    relinked_details = []

    for file_path in original_dir.rglob('*'):
        if file_path.is_symlink() or not file_path.is_file():
            continue

        if not is_supported_file(file_path.name):
            continue

        try:
            abs_path = str(file_path.resolve())
            if abs_path in existing_tracked_paths:
                continue

            mime_type = get_mime_type(file_path)
            if not mime_type.startswith('image/') and not mime_type.startswith('video/') and mime_type not in ('application/x-matroska', 'application/vnd.rn-realmedia'):
                continue

            file_hash = calculate_file_hash(file_path)
            if file_hash in missing_media_by_hash:
                media = missing_media_by_hash.pop(file_hash)
                old_path = media.path
                old_filename = media.filename
                new_rel_path = str(file_path.relative_to(base_dir))
                new_filename = file_path.name

                media.path = new_rel_path
                media.filename = new_filename

                # Handle transcoding if needed
                fmt = format_registry.get_format(file_path.name)
                transcoded_file = None
                if fmt and fmt.requires_transcode:
                    expected_transcoded = get_transcoded_path_for_original(file_path, fmt.transcode_target)
                    old_transcoded = (base_dir / media.transcoded_path) if media.transcoded_path else None

                    # If previous transcoded file exists on disk, move/rename it
                    if old_transcoded and old_transcoded.exists() and old_transcoded.is_file():
                        if old_transcoded.resolve() != expected_transcoded.resolve():
                            expected_transcoded.parent.mkdir(parents=True, exist_ok=True)
                            import shutil
                            shutil.move(str(old_transcoded), str(expected_transcoded))
                        media.transcoded_path = str(expected_transcoded.relative_to(base_dir))
                        transcoded_file = expected_transcoded
                    elif expected_transcoded.exists() and expected_transcoded.is_file():
                        media.transcoded_path = str(expected_transcoded.relative_to(base_dir))
                        transcoded_file = expected_transcoded
                    else:
                        transcoded_file = transcode_media_if_needed(file_path)
                        if transcoded_file:
                            media.transcoded_path = str(transcoded_file.relative_to(base_dir))
                else:
                    if media.transcoded_path:
                        old_transcoded = base_dir / media.transcoded_path
                        if old_transcoded.exists() and old_transcoded.is_file():
                            old_transcoded.unlink(missing_ok=True)
                        media.transcoded_path = None

                # Check thumbnail health
                thumb_missing = True
                if media.thumbnail_path:
                    thumb_abs = base_dir / media.thumbnail_path
                    if thumb_abs.exists() and thumb_abs.is_file():
                        thumb_missing = False

                if thumb_missing:
                    hash_thumb = thumbnail_dir / f"{media.hash}{THUMBNAIL_EXT}"
                    stem_thumb = thumbnail_dir / f"{Path(new_filename).stem}{THUMBNAIL_EXT}"
                    if hash_thumb.exists():
                        media.thumbnail_path = str(hash_thumb.relative_to(base_dir))
                    elif stem_thumb.exists():
                        media.thumbnail_path = str(stem_thumb.relative_to(base_dir))
                    else:
                        try:
                            thumb_src = transcoded_file if transcoded_file else file_path
                            if generate_thumbnail(thumb_src, hash_thumb, media.file_type):
                                media.thumbnail_path = str(hash_thumb.relative_to(base_dir))
                            else:
                                media.thumbnail_path = None
                        except Exception as e:
                            logger.error(f"Error generating thumbnail during relink for {media.id}: {e}")
                            media.thumbnail_path = None

                relinked_details.append({
                    'id': media.id,
                    'old_path': old_path,
                    'new_path': new_rel_path,
                    'filename': new_filename
                })
                existing_tracked_paths.add(abs_path)
                invalidate_media_item_cache(media.id)

                if not missing_media_by_hash:
                    break

        except Exception as e:
            logger.error(f"Error checking file {file_path.name} during relink: {str(e)}")
            continue

    if relinked_details:
        db.commit()
        invalidate_media_cache()

    logger.info(f"Relink complete: {len(relinked_details)} relinked, {len(missing_media_by_hash)} unresolved")

    return {
        'relinked': len(relinked_details),
        'unresolved': len(missing_media_by_hash),
        'total_checked': len(all_media),
        'details': relinked_details
    }
