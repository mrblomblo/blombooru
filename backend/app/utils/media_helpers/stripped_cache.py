import asyncio
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from PIL import Image
from fastapi.concurrency import run_in_threadpool
from .. import image_plugins
from ..format_registry import format_registry
from ..logger import logger
from .paths import get_effective_media_path

_cache_locks: Dict[str, list] = {}

def touch_cache_file(path: Path) -> None:
    """Update access and modification time of a cache file on access to support LRU eviction."""
    try:
        os.utime(path, None)
    except OSError:
        pass

def get_stripped_cache_path(media: Any, mime_type: Optional[str] = None) -> Path:
    """Return the path to the metadata-stripped cache file for a given media item."""
    from ...config import settings
    stripped_dir = getattr(settings, "STRIPPED_CACHE_DIR", settings.CACHE_DIR / "stripped")
    if hasattr(media, "hash") and media.hash:
        effective_path = get_effective_media_path(media)
        ext = Path(effective_path.name).suffix
        return stripped_dir / f"{media.hash}{ext}"
    elif isinstance(media, (Path, str)):
        p = Path(media)
        from ..media_processor import calculate_file_hash
        if p.exists():
            h = calculate_file_hash(p)
            return stripped_dir / f"{h}{p.suffix}"
        return stripped_dir / f"{p.stem}{p.suffix}"
    raise ValueError("Invalid media or path provided to get_stripped_cache_path")

def find_and_migrate_legacy_cache_file(media_or_path: Any, target_path: Path) -> bool:
    """
    Check if a legacy stripped cache file exists directly in settings.CACHE_DIR
    for this media and seamlessly move/rename it to target_path.
    """
    from ...config import settings
    if not settings.CACHE_DIR.exists():
        return False

    effective_path = get_effective_media_path(media_or_path) if hasattr(media_or_path, "hash") else Path(media_or_path)
    names_to_check = {effective_path.name}
    if hasattr(media_or_path, "path"):
        names_to_check.add(Path(media_or_path.path).name)
    if hasattr(media_or_path, "filename"):
        names_to_check.add(media_or_path.filename)

    try:
        for entry in settings.CACHE_DIR.iterdir():
            if entry.is_dir() or entry.is_symlink() or not entry.is_file() or entry.suffix == ".tmp":
                continue
            parts = entry.name.split('_', 1)
            if len(parts) == 2 and parts[1] in names_to_check:
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    entry.replace(target_path)
                    logger.info(f"Seamlessly migrated legacy cache file: {entry.name} -> {target_path.name}")
                    return True
                except OSError as e:
                    logger.error(f"Error migrating legacy cache file {entry}: {e}")
    except OSError:
        pass
    return False

async def create_stripped_media_cache(media_or_path: Any, mime_type: str) -> Optional[Path]:
    """
    Create a metadata-stripped version of the media file in the cache.
    Returns the path to the cached file, or None if stripping is not supported/failed.
    """
    if not mime_type or not mime_type.startswith('image/'):
        return None
        
    from ...config import settings
    
    effective_path = get_effective_media_path(media_or_path) if hasattr(media_or_path, 'hash') else Path(media_or_path)
    if not effective_path.exists():
        return None

    cache_path = get_stripped_cache_path(media_or_path, mime_type)
    
    # Ensure cache directory exists
    if not cache_path.parent.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Return cached file if it exists
    if cache_path.exists():
        touch_cache_file(cache_path)
        return cache_path

    # Try on-demand seamless migration from legacy cache
    if find_and_migrate_legacy_cache_file(media_or_path, cache_path):
        touch_cache_file(cache_path)
        return cache_path

    lock_key = getattr(media_or_path, "hash", None) or cache_path.stem
    if lock_key not in _cache_locks:
        _cache_locks[lock_key] = [asyncio.Lock(), 0]
    entry = _cache_locks[lock_key]
    entry[1] += 1
    lock = entry[0]

    try:
        async with lock:
            # Check again after acquiring lock to deduplicate concurrent generation
            if cache_path.exists():
                touch_cache_file(cache_path)
                return cache_path
            if find_and_migrate_legacy_cache_file(media_or_path, cache_path):
                touch_cache_file(cache_path)
                return cache_path

            # Run image processing in threadpool to avoid blocking event loop
            def process_image():
                with Image.open(effective_path) as img:
                    # Check if image is animated
                    is_animated = getattr(img, 'is_animated', False)
                    n_frames = getattr(img, 'n_frames', 1)
                    
                    # Extract frame durations for animated images
                    frame_durations = []
                    if is_animated and n_frames > 1:
                        try:
                            if img.format == 'WEBP':                                
                                # Try different metadata fields
                                timestamp = img.info.get('timestamp', None)
                                
                                if timestamp:
                                    # Calculate average frame duration from total timestamp
                                    avg_duration = int(timestamp / n_frames) if n_frames > 0 else 100
                                    frame_durations = [avg_duration] * n_frames
                                else:
                                    # Fallback: iterate through frames and collect durations
                                    for frame_idx in range(n_frames):
                                        img.seek(frame_idx)
                                        duration = img.info.get('duration', 100)
                                        frame_durations.append(duration)
                                    img.seek(0)
                            else:
                                # For GIF and other formats, standard extraction
                                for frame_idx in range(n_frames):
                                    img.seek(frame_idx)
                                    duration = img.info.get('duration', 100)
                                    frame_durations.append(duration)
                                img.seek(0)
                            
                        except Exception as e:
                            logger.error(f"Error extracting frame durations: {e}")
                            frame_durations = [100] * n_frames  # Fallback to 100ms per frame
                    
                    # Convert RGBA to RGB if necessary (for JPEG output)
                    if mime_type == 'image/jpeg' and img.mode in ('RGBA', 'LA', 'P'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                        img = background
                    
                    # Determine format from mime type
                    format_map = {
                        'image/jpeg': 'JPEG',
                        'image/png': 'PNG',
                        'image/gif': 'GIF',
                        'image/webp': 'WEBP',
                        'image/bmp': 'BMP',
                    }
                    
                    save_format = format_map.get(mime_type, 'PNG')
                    
                    # Save without metadata
                    save_kwargs = {
                        'format': save_format,
                        'optimize': True,
                    }
                    
                    # Format-specific options
                    if save_format == 'JPEG':
                        save_kwargs['quality'] = 95
                        save_kwargs['exif'] = b''  # Empty EXIF data
                    elif save_format == 'PNG':
                        save_kwargs['compress_level'] = 6
                        # PNG doesn't save EXIF by default, but we ensure no chunks
                        save_kwargs['pnginfo'] = None
                    elif save_format == 'WEBP':
                        save_kwargs['quality'] = 95
                        save_kwargs['exif'] = b''
                        
                        # Preserve animation for WebP
                        if is_animated and n_frames > 1:
                            save_kwargs['save_all'] = True
                            # Use the extracted frame durations
                            if frame_durations:
                                save_kwargs['duration'] = frame_durations
                            else:
                                save_kwargs['duration'] = 100
                    elif save_format == 'GIF':
                        # Preserve animation for GIF
                        if is_animated and n_frames > 1:
                            save_kwargs['save_all'] = True
                            # Use the extracted frame durations
                            if frame_durations:
                                save_kwargs['duration'] = frame_durations
                            else:
                                save_kwargs['duration'] = 100
                            # Preserve loop count
                            try:
                                loop = img.info.get('loop', 0)
                                save_kwargs['loop'] = loop
                            except Exception:
                                save_kwargs['loop'] = 0
                    
                    # Save to a temporary file first to ensure atomicity using unique filename to avoid race conditions
                    temp_cache_path = cache_path.with_suffix(f'.{uuid.uuid4()}.tmp')
                    try:
                        img.save(temp_cache_path, **save_kwargs)
                        
                        # Atomic rename
                        temp_cache_path.replace(cache_path)
                    except Exception as save_err:
                        # Clean up temp file on error
                        if temp_cache_path.exists():
                            try:
                                temp_cache_path.unlink()
                            except Exception:
                                pass
                        raise save_err
            
            await run_in_threadpool(process_image)
            await run_in_threadpool(evict_stripped_cache_if_needed)
            return cache_path
                
    except Exception as e:
        logger.error(f"Error stripping metadata from {effective_path}: {e}", exc_info=True)
        return None
    finally:
        entry[1] -= 1
        if entry[1] <= 0:
            if _cache_locks.get(lock_key) is entry:
                _cache_locks.pop(lock_key, None)

async def rebuild_stripped_cache_if_needed(media: Any, background_tasks: Any = None) -> Optional[Path]:
    """
    If the media is shared, has metadata stripping enabled (share_ai_metadata=False), 
    and is an image, automatically rebuild its stripped cache file.
    """
    if not getattr(media, "is_shared", False) or getattr(media, "share_ai_metadata", False):
        return None
    effective_path = get_effective_media_path(media)
    if not effective_path.exists():
        return None
    from ..format_registry import format_registry
    effective_mime = format_registry.get_mime_type(effective_path.name, default=getattr(media, "mime_type", ""))
    if not effective_mime or not effective_mime.startswith("image/"):
        return None

    # Delete existing cache file if present to guarantee a fresh rebuild
    delete_media_cache(media)

    if background_tasks is not None:
        background_tasks.add_task(create_stripped_media_cache, media, effective_mime)
        return None
    return await create_stripped_media_cache(media, effective_mime)

def delete_media_cache(media_or_path: Any):
    """Delete the cached version of a media file if it exists."""
    import hashlib
    from ...config import settings
    
    try:
        stripped_dir = getattr(settings, "STRIPPED_CACHE_DIR", settings.CACHE_DIR / "stripped")
        deleted_any = False
        target_desc = str(media_or_path)

        if hasattr(media_or_path, "hash") and media_or_path.hash:
            media_hash = media_or_path.hash
            target_desc = f"media hash={media_hash}"
            if stripped_dir.exists():
                for f in stripped_dir.glob(f"{media_hash}.*"):
                    if f.is_file():
                        try:
                            f.unlink(missing_ok=True)
                            deleted_any = True
                            logger.debug(f"Deleted cache file: {f}")
                        except OSError as unlink_err:
                            logger.error(f"Error unlinking cache file {f}: {unlink_err}")

            # Also check legacy cache files in settings.CACHE_DIR
            if settings.CACHE_DIR.exists():
                try:
                    eff_path = get_effective_media_path(media_or_path)
                    names_to_check = {eff_path.name}
                    if hasattr(media_or_path, "path"):
                        names_to_check.add(Path(media_or_path.path).name)
                    if hasattr(media_or_path, "filename"):
                        names_to_check.add(media_or_path.filename)
                    for f in settings.CACHE_DIR.iterdir():
                        if f.is_file() and not f.is_dir() and f.suffix != ".tmp":
                            parts = f.name.split('_', 1)
                            if len(parts) == 2 and parts[1] in names_to_check:
                                f.unlink(missing_ok=True)
                                deleted_any = True
                                logger.debug(f"Deleted legacy cache file: {f}")
                except Exception:
                    pass

        elif isinstance(media_or_path, (Path, str)):
            file_path = Path(media_or_path)
            target_desc = str(file_path)
            # If file_path is directly in stripped_dir
            if stripped_dir.exists() and file_path.parent.resolve() == stripped_dir.resolve() and file_path.exists():
                file_path.unlink(missing_ok=True)
                deleted_any = True
                logger.debug(f"Deleted cache file: {file_path}")
            else:
                if file_path.exists():
                    try:
                        from ..media_processor import calculate_file_hash
                        h = calculate_file_hash(file_path)
                        if stripped_dir.exists():
                            for f in stripped_dir.glob(f"{h}.*"):
                                if f.is_file():
                                    try:
                                        f.unlink(missing_ok=True)
                                        deleted_any = True
                                        logger.debug(f"Deleted cache file: {f}")
                                    except OSError as unlink_err:
                                        logger.error(f"Error unlinking cache file {f}: {unlink_err}")
                    except Exception:
                        pass

                if settings.CACHE_DIR.exists():
                    try:
                        names_to_check = {file_path.name}
                        for f in settings.CACHE_DIR.iterdir():
                            if f.is_file() and not f.is_dir() and f.suffix != ".tmp":
                                parts = f.name.split('_', 1)
                                if len(parts) == 2 and parts[1] in names_to_check:
                                    f.unlink(missing_ok=True)
                                    deleted_any = True
                                    logger.debug(f"Deleted legacy cache file: {f}")
                    except Exception:
                        pass

        if not deleted_any:
            logger.debug(f"No cache entry found for {target_desc}")

    except Exception as e:
        logger.error(f"Error deleting media cache for {media_or_path}: {e}")

def migrate_legacy_stripped_cache(db) -> dict:
    """
    Seamlessly migrate legacy stripped cache files from media/cache/ into media/cache/stripped/.
    Any legacy file corresponding to an active shared media without AI metadata is migrated.
    Any unused legacy files (media not found, unshared, or AI metadata shared) are removed.
    Returns: {"migrated": int, "removed": int}
    """
    from ...config import settings
    from ...models import Media

    stripped_dir = getattr(settings, "STRIPPED_CACHE_DIR", settings.CACHE_DIR / "stripped")
    if not settings.CACHE_DIR.exists():
        return {"migrated": 0, "removed": 0}

    stripped_dir.mkdir(parents=True, exist_ok=True)

    legacy_files = []
    try:
        for entry in settings.CACHE_DIR.iterdir():
            if entry.is_dir() or entry.is_symlink() or not entry.is_file():
                continue
            if entry.suffix == ".tmp":
                continue
            legacy_files.append(entry)
    except OSError as e:
        logger.error(f"migrate_legacy_stripped_cache: directory scan failed: {e}")
        return {"migrated": 0, "removed": 0}

    if not legacy_files:
        return {"migrated": 0, "removed": 0}

    migrated = 0
    removed = 0

    try:
        all_shared = db.query(Media).filter(
            Media.is_shared == True
        ).all()
        active_map: dict[str, Media] = {}
        for m in all_shared:
            if getattr(m, "share_ai_metadata", False) or not m.hash:
                continue
            eff_path = get_effective_media_path(m)
            active_map[eff_path.name] = m
            if m.path:
                active_map[Path(m.path).name] = m
            if m.filename:
                active_map[m.filename] = m
    except Exception as e:
        logger.error(f"migrate_legacy_stripped_cache: DB query failed: {e}")
        return {"migrated": 0, "removed": 0}

    for entry in legacy_files:
        parts = entry.name.split('_', 1)
        media_match = None
        if len(parts) == 2:
            media_match = active_map.get(parts[1])

        if media_match:
            target_path = get_stripped_cache_path(media_match)
            if target_path.exists():
                try:
                    entry.unlink(missing_ok=True)
                    removed += 1
                    logger.debug(f"Removed redundant legacy cache file: {entry.name}")
                except OSError as err:
                    logger.error(f"Error removing redundant legacy file {entry}: {err}")
            else:
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    entry.replace(target_path)
                    migrated += 1
                    logger.info(f"Migrated legacy stripped cache file: {entry.name} -> {target_path.name}")
                except OSError as err:
                    logger.error(f"Error migrating legacy cache file {entry}: {err}")
        else:
            try:
                entry.unlink(missing_ok=True)
                removed += 1
                logger.debug(f"Removed unused legacy stripped cache file: {entry.name}")
            except OSError as err:
                logger.error(f"Error removing unused legacy file {entry}: {err}")

    if migrated:
        logger.info(f"Migrated {migrated} legacy stripped cache file(s) to {stripped_dir}")
    if removed:
        logger.info(f"Removed {removed} unused legacy stripped cache file(s)")

    return {"migrated": migrated, "removed": removed}

def cleanup_dead_media_cache(db) -> int:
    """
    Remove cache files that no longer correspond to any media in the database,
    and migrate any legacy stripped cache files to the new system.
    Returns total number of deleted/removed unused files.
    """
    from ...config import settings
    from ...models import Media
    
    stripped_dir = getattr(settings, "STRIPPED_CACHE_DIR", settings.CACHE_DIR / "stripped")
    if not settings.CACHE_DIR.exists() and not stripped_dir.exists():
        return 0

    # Migrate legacy cache files and remove unused legacy ones
    migration_result = migrate_legacy_stripped_cache(db)
    deleted = migration_result["removed"]

    try:
        all_shared = db.query(Media).filter(
            Media.is_shared == True
        ).all()
        # A cache entry is valid if media exists in DB, is shared, and AI metadata is not shared
        valid_hashes = {
            m.hash for m in all_shared
            if m.hash and not getattr(m, "share_ai_metadata", False)
        }
    except Exception as e:
        logger.error(f"cleanup_dead_media_cache: DB query failed: {e}")
        return deleted

    # Clean dead/unused entries in stripped_dir
    if stripped_dir.exists():
        try:
            for entry in stripped_dir.iterdir():
                if entry.is_dir() or entry.is_symlink() or not entry.is_file():
                    continue
                # Leave in-progress atomic write temps alone
                if entry.suffix == ".tmp":
                    continue
                # entry.stem is the content hash
                if entry.stem not in valid_hashes:
                    try:
                        entry.unlink()
                        deleted += 1
                        logger.debug(f"Removed unused stripped cache file: {entry.name}")
                    except FileNotFoundError:
                        pass
                    except Exception as unlink_err:
                        logger.error(f"Error removing dead cache file {entry}: {unlink_err}")
        except Exception as e:
            logger.error(f"cleanup_dead_media_cache: directory scan failed for {stripped_dir}: {e}")

    if deleted:
        logger.info(f"Dead cache cleanup: removed {deleted} unused file(s) from cache")

    return deleted

def get_media_cache_status(media_or_path: Any, mime_type: str) -> str:
    """
    Check the status of the media cache file.
    Returns: 'ready', 'processing', 'not_stripped', or 'error'.
    """
    if not mime_type or not mime_type.startswith('image/'):
        return 'not_stripped'
        
    try:
        effective_path = get_effective_media_path(media_or_path) if hasattr(media_or_path, 'hash') else Path(media_or_path)
        if not effective_path.exists():
            return 'error'

        cache_path = get_stripped_cache_path(media_or_path, mime_type)
        if cache_path.exists():
            return 'ready'

        # Check if a legacy cache file exists and migrate it seamlessly
        if find_and_migrate_legacy_cache_file(media_or_path, cache_path):
            return 'ready'
            
        return 'processing'
    except Exception as e:
        logger.error(f"Error checking media cache status: {e}")
        return 'error'

def get_stripped_cache_stats() -> dict:
    """Return file count and total size in bytes for media/cache/stripped/."""
    from ...config import settings
    stripped_dir = getattr(settings, "STRIPPED_CACHE_DIR", settings.CACHE_DIR / "stripped")
    if not stripped_dir.exists():
        return {"count": 0, "size_bytes": 0}
    
    count = 0
    total_bytes = 0
    try:
        for entry in stripped_dir.iterdir():
            if entry.is_file() and not entry.is_symlink() and entry.suffix != ".tmp":
                count += 1
                try:
                    total_bytes += entry.stat().st_size
                except OSError:
                    pass
    except OSError as e:
        logger.error(f"Error reading stripped cache directory: {e}")
        
    return {"count": count, "size_bytes": total_bytes}

def evict_stripped_cache_if_needed(max_mb: Optional[int] = None) -> int:
    """
    If the stripped cache exceeds max_mb (or settings.STRIPPED_CACHE_MAX_MB if None),
    evict least-recently-used (oldest access mtime) entries until cache is within limit.
    Returns number of evicted files.
    """
    from ...config import settings
    if max_mb is None:
        max_mb = getattr(settings, "STRIPPED_CACHE_MAX_MB", 0)
    if not max_mb or max_mb <= 0:
        return 0
        
    max_bytes = max_mb * 1024 * 1024
    stripped_dir = getattr(settings, "STRIPPED_CACHE_DIR", settings.CACHE_DIR / "stripped")
    if not stripped_dir.exists():
        return 0
        
    entries = []
    total_bytes = 0
    try:
        for entry in stripped_dir.iterdir():
            if entry.is_file() and not entry.is_symlink() and entry.suffix != ".tmp":
                try:
                    st = entry.stat()
                    entries.append((st.st_mtime, st.st_size, entry))
                    total_bytes += st.st_size
                except OSError:
                    continue
    except OSError as e:
        logger.error(f"Error scanning stripped cache directory for eviction: {e}")
        return 0
                
    if total_bytes <= max_bytes:
        return 0
        
    # Sort oldest mtime first
    entries.sort(key=lambda x: x[0])
    evicted = 0
    for _, size, entry in entries:
        try:
            entry.unlink()
            evicted += 1
            total_bytes -= size
            logger.debug(f"LRU evicted stripped cache file: {entry.name}")
            if total_bytes <= max_bytes:
                break
        except OSError:
            pass
            
    if evicted:
        logger.info(f"Stripped cache LRU eviction: removed {evicted} file(s) to reach target size")
    return evicted
