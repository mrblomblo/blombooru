import json
import mimetypes
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
from fastapi import HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ExifTags

from .ai_metadata import decode_exif_user_comment, normalize_ai_metadata, parse_xmp_packet
from .format_registry import format_registry
from .logger import logger

def extract_image_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract metadata from media files (EXIF, PNG chunks, XMP, etc.)"""
    metadata: Dict[str, Any] = {}

    # Verify file is an image using format_registry or mimetypes
    if not format_registry.is_image(file_path):
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type or not mime_type.startswith('image/'):
            return metadata

    # Record file-level stats
    try:
        stat = file_path.stat()
        metadata['file_size'] = stat.st_size
        metadata['file_type'] = 'image'
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            metadata['mime_type'] = mime_type
    except Exception as e:
        logger.debug(f"Error getting file stat for {file_path}: {e}")

    try:
        container_parameters = None
        sub_ifd_user_comment = None
        ifd0_user_comment = None
        image_description = None
        xmp_comment = None
        xp_comment_val = None
        legacy_user_comment = None
        raw_prompt_graph = None
        raw_text_prompt = None

        with Image.open(file_path) as img:
            try:
                metadata['width'], metadata['height'] = img.size
            except Exception:
                pass

            # Get PNG text chunks
            if hasattr(img, 'info') and img.info:
                ignored_binary_keys = {'icc_profile', 'photoshop', 'exif', 'adobe', 'adobe_transform'}

                for key, value in img.info.items():
                    if key in ignored_binary_keys:
                        continue

                    if isinstance(value, str):
                        try:
                            parsed_val = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            parsed_val = value
                    elif isinstance(value, bytes):
                        # If XMP chunk, parse XML packet
                        if key.lower() in ('xmp', 'xml:com.adobe.xmp'):
                            try:
                                parsed_xmp = parse_xmp_packet(value)
                                if parsed_xmp:
                                    metadata['xmp'] = parsed_xmp
                            except Exception as e:
                                logger.debug(f"Error parsing XMP chunk in {file_path}: {e}")
                            continue

                        try:
                            decoded = value.decode('utf-8', errors='replace').replace('\x00', '').strip()
                            try:
                                parsed_val = json.loads(decoded)
                            except (json.JSONDecodeError, ValueError):
                                parsed_val = decoded
                        except Exception:
                            continue
                    else:
                        parsed_val = value

                    # Quarantine prompt chunk to avoid collisions with the canonical human prompt field
                    if key.lower() == 'prompt':
                        if isinstance(parsed_val, (dict, list)):
                            raw_prompt_graph = parsed_val
                        elif isinstance(parsed_val, str) and parsed_val.strip():
                            raw_text_prompt = parsed_val.strip()
                        continue

                    metadata[key] = parsed_val

                if 'parameters' in metadata and metadata['parameters']:
                    container_parameters = metadata['parameters']

            # Extract potential parameter candidates from parsed XMP
            if 'xmp' in metadata and isinstance(metadata['xmp'], dict):
                xmp_dict = metadata['xmp']
                for xmp_k in ('UserComment', 'parameters', 'prompt', 'Description', 'description'):
                    if xmp_k in xmp_dict and xmp_dict[xmp_k]:
                        xmp_comment = xmp_dict[xmp_k]
                        break

            # Extract EXIF tags
            if hasattr(img, 'getexif'):
                try:
                    exif = img.getexif()
                except Exception as e:
                    logger.debug(f"Error calling getexif on {file_path}: {e}")
                    exif = None

                if exif:
                    # ComfyUI WebP often stores 'workflow:{...}' in Make and 'prompt:{...}' in Model
                    try:
                        for tag_id, key_name in ((271, 'workflow'), (272, 'prompt')):
                            if tag_id in exif:
                                val = exif[tag_id]
                                if isinstance(val, str) and val.startswith(f"{key_name}:"):
                                    raw_json = val[len(key_name) + 1:]
                                    try:
                                        parsed_exif = json.loads(raw_json)
                                    except Exception:
                                        parsed_exif = raw_json

                                    if key_name == 'prompt':
                                        if isinstance(parsed_exif, (dict, list)):
                                            if raw_prompt_graph is None:
                                                raw_prompt_graph = parsed_exif
                                        elif isinstance(parsed_exif, str) and parsed_exif.strip():
                                            if raw_text_prompt is None:
                                                raw_text_prompt = parsed_exif.strip()
                                    else:
                                        metadata[key_name] = parsed_exif
                    except Exception:
                        pass

                    # ImageDescription tag (0x010E / 270)
                    try:
                        if 0x010E in exif:
                            desc_raw = exif[0x010E]
                            desc_str = decode_exif_user_comment(desc_raw) if isinstance(desc_raw, bytes) else str(desc_raw).strip()
                            if desc_str:
                                try:
                                    image_description = json.loads(desc_str)
                                except (json.JSONDecodeError, ValueError):
                                    image_description = desc_str
                                metadata['description'] = image_description
                    except Exception:
                        pass

                    # UserComment tag in IFD0 (0x9286 / 37510)
                    try:
                        if 0x9286 in exif:
                            uc_text = decode_exif_user_comment(exif[0x9286])
                            if uc_text:
                                try:
                                    ifd0_user_comment = json.loads(uc_text)
                                except (json.JSONDecodeError, ValueError):
                                    ifd0_user_comment = uc_text
                                metadata['user_comment'] = uc_text
                    except Exception:
                        pass

                    # XPComment tag (0x9C9C / 40092) - Windows comment field
                    try:
                        if 0x9C9C in exif:
                            raw_xp = exif[0x9C9C]
                            if isinstance(raw_xp, bytes):
                                decoded_xp = raw_xp.decode('utf-16le', errors='replace').replace('\x00', '').strip()
                                if decoded_xp:
                                    try:
                                        xp_comment_val = json.loads(decoded_xp)
                                    except (json.JSONDecodeError, ValueError):
                                        xp_comment_val = decoded_xp
                                    metadata['xp_comment'] = decoded_xp
                    except Exception:
                        pass

                    # XPKeywords tag (0x9C9E / 40094)
                    try:
                        if 0x9C9E in exif:
                            raw_kw = exif[0x9C9E]
                            if isinstance(raw_kw, bytes):
                                decoded_kw = raw_kw.decode('utf-16le', errors='replace').replace('\x00', '').strip()
                                if decoded_kw:
                                    try:
                                        metadata['keywords'] = json.loads(decoded_kw)
                                    except (json.JSONDecodeError, ValueError):
                                        metadata['keywords'] = decoded_kw
                    except Exception:
                        pass

                    # Exif Sub-IFD (0x8769 / ExifTags.IFD.Exif)
                    # This is where UserComment (0x9286) standardly resides!
                    try:
                        exif_sub_ifd = exif.get_ifd(ExifTags.IFD.Exif)
                        if exif_sub_ifd and 0x9286 in exif_sub_ifd:
                            uc_sub = decode_exif_user_comment(exif_sub_ifd[0x9286])
                            if uc_sub:
                                try:
                                    sub_ifd_user_comment = json.loads(uc_sub)
                                except (json.JSONDecodeError, ValueError):
                                    sub_ifd_user_comment = uc_sub
                                metadata['user_comment'] = uc_sub
                    except Exception:
                        pass
            
            # Legacy EXIF method
            if hasattr(img, '_getexif') and callable(img._getexif):
                try:
                    legacy_exif = img._getexif()
                    if legacy_exif and 0x9286 in legacy_exif:
                        legacy_text = decode_exif_user_comment(legacy_exif[0x9286])
                        if legacy_text:
                            try:
                                legacy_user_comment = json.loads(legacy_text)
                            except (json.JSONDecodeError, ValueError):
                                legacy_user_comment = legacy_text
                except Exception:
                    pass

        # Strict priority order for metadata['parameters']:
        # 1. Native container text chunk (parameters from img.info)
        # 2. EXIF Sub-IFD UserComment (0x8769 -> 0x9286)
        # 3. EXIF IFD0 UserComment (0x9286)
        # 4. EXIF IFD0 ImageDescription (0x010E)
        # 5. XMP packet (UserComment, parameters, Description, etc.)
        # 6. EXIF Windows XPComment (0x9C9C)
        # 7. Legacy _getexif fallback
        selected_params = (
            container_parameters
            or sub_ifd_user_comment
            or ifd0_user_comment
            or image_description
            or xmp_comment
            or xp_comment_val
            or legacy_user_comment
        )
        if selected_params is not None:
            metadata['parameters'] = selected_params

        # Prepare dictionary for normalizer with quarantined graph if available
        meta_to_normalize = dict(metadata)
        if raw_prompt_graph is not None and 'prompt' not in meta_to_normalize:
            meta_to_normalize['prompt'] = raw_prompt_graph
        elif raw_text_prompt is not None and 'prompt' not in meta_to_normalize:
            meta_to_normalize['prompt'] = raw_text_prompt

        # Normalize AI metadata using the dedicated ai_metadata normalizer
        normalized = normalize_ai_metadata(meta_to_normalize)
        if normalized:
            # Extended dedup check: avoid duplicating workflow/prompt graph
            if 'workflow' in normalized:
                norm_wf = normalized['workflow']
                if ('workflow' in metadata and (metadata['workflow'] == norm_wf or metadata['workflow'] is norm_wf or 'workflow' in metadata)) or \
                   ('prompt' in metadata and (metadata['prompt'] == norm_wf or metadata['prompt'] is norm_wf)):
                    normalized.pop('workflow', None)

            metadata['ai'] = normalized

            # Set metadata['prompt'] only to the extracted human prompt text string
            if normalized.get('prompt') and isinstance(normalized['prompt'], str):
                metadata['prompt'] = normalized['prompt']
            elif raw_text_prompt and isinstance(raw_text_prompt, str):
                metadata['prompt'] = raw_text_prompt
        elif raw_text_prompt and isinstance(raw_text_prompt, str):
            metadata['prompt'] = raw_text_prompt

        # Ensure metadata['prompt'] is never a dict or list
        if isinstance(metadata.get('prompt'), (dict, list)):
            metadata.pop('prompt', None)

        return metadata
        
    except Exception as e:
        logger.error(f"Error reading metadata from {file_path}: {e}", exc_info=True)
        return metadata

def extract_video_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract metadata from video files."""
    metadata = {}
    
    try:
        vid = cv2.VideoCapture(str(file_path))
        if vid.isOpened():
            metadata['width'] = int(vid.get(cv2.CAP_PROP_FRAME_WIDTH))
            metadata['height'] = int(vid.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            frame_count = int(vid.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = vid.get(cv2.CAP_PROP_FPS)
            
            metadata['frame_count'] = frame_count
            metadata['fps'] = fps
            
            if fps > 0:
                metadata['duration'] = frame_count / fps
            
            vid.release()
    except Exception as e:
        logger.error(f"Error reading video metadata with cv2 for {file_path}: {e}")

    try:
        stat = file_path.stat()
        metadata['file_size'] = stat.st_size
        metadata['file_type'] = 'video'
        
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            metadata['mime_type'] = mime_type
            
    except Exception as e:
        logger.error(f"Error getting video metadata for {file_path}: {e}")
    
    return metadata

def extract_media_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract metadata from any media file (image or video)."""
    if format_registry.is_video(file_path):
        return extract_video_metadata(file_path)
    if format_registry.is_image(file_path):
        return extract_image_metadata(file_path)

    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type:
        if mime_type.startswith('video/'):
            return extract_video_metadata(file_path)
        elif mime_type.startswith('image/'):
            return extract_image_metadata(file_path)
    
    # Final fallback: try image first, then video
    res = extract_image_metadata(file_path)
    if res:
        return res
    return extract_video_metadata(file_path)

async def create_stripped_media_cache(file_path: Path, mime_type: str) -> Optional[Path]:
    """
    Create a metadata-stripped version of the media file in the cache.
    Returns the path to the cached file, or None if stripping is not supported/failed.
    """
    if not mime_type or not mime_type.startswith('image/'):
        return None
        
    import hashlib

    from fastapi.concurrency import run_in_threadpool

    from ..config import settings
    
    stat = file_path.stat()
    cache_key = f"{str(file_path)}_{stat.st_mtime}"
    cache_filename = hashlib.md5(cache_key.encode()).hexdigest() + "_" + file_path.name
    cache_path = settings.CACHE_DIR / cache_filename
    
    # Ensure cache directory exists (in case it was deleted)
    if not cache_path.parent.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Return cached file if it exists
    if cache_path.exists():
        return cache_path
        
    try:
        # Run image processing in threadpool to avoid blocking event loop
        def process_image():
            with Image.open(file_path) as img:
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
        return cache_path
            
    except Exception as e:
        logger.error(f"Error stripping metadata from {file_path}: {e}", exc_info=True)
        return None

class ChunkedMediaResponse(FileResponse):
    """FileResponse subclass with Range request capping and optional video initial chunking."""
    MAX_RANGE_SIZE = 25 * 1024 * 1024       # 25 MB
    INITIAL_VIDEO_CHUNK = 2 * 1024 * 1024   # 2 MB

    def __init__(self, *args, chunked: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.chunked = chunked

    @staticmethod
    def _parse_range_header(http_range: str, file_size: int) -> list[tuple[int, int]]:
        from starlette.responses import FileResponse
        ranges = FileResponse._parse_range_header(http_range, file_size)
        
        capped_ranges = []
        for start, end in ranges:
            if end - start > ChunkedMediaResponse.MAX_RANGE_SIZE:
                end = start + ChunkedMediaResponse.MAX_RANGE_SIZE
            capped_ranges.append((start, end))
            
        return capped_ranges

    async def __call__(self, scope, receive, send) -> None:
        headers = dict(scope.get("headers", []))
        # Opt-in: inject a bounded initial range for videos to avoid connection starvation
        if self.chunked and b"range" not in headers:
            is_video = self.media_type and self.media_type.startswith("video/")
            if is_video:
                end_byte = self.INITIAL_VIDEO_CHUNK - 1
                scope["headers"].append((b"range", f"bytes=0-{end_byte}".encode()))
        await super().__call__(scope, receive, send)

async def serve_media_file(
    file_path: Path,
    mime_type: str,
    error_message: str = "File not found",
    strip_metadata: bool = False,
    chunked: bool = False,
    download: bool = False,
    filename: Optional[str] = None,
) -> FileResponse:
    """Serve a media file with error handling, optional metadata stripping, and browser caching."""
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=error_message)
    
    cache_headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    content_disposition_type = "attachment" if download else "inline"
    download_filename = filename or file_path.name if download else None
    
    if not strip_metadata:
        return ChunkedMediaResponse(
            file_path,
            media_type=mime_type,
            headers=cache_headers,
            chunked=chunked,
            filename=download_filename,
            content_disposition_type=content_disposition_type
        )
    
    if mime_type and mime_type.startswith('image/'):
        cache_path = await create_stripped_media_cache(file_path, mime_type)
        if cache_path:
            return ChunkedMediaResponse(
                cache_path,
                media_type=mime_type,
                headers=cache_headers,
                chunked=chunked,
                filename=download_filename,
                content_disposition_type=content_disposition_type
            )
    
    # Fallback to file if stripping not supported or failed
    return ChunkedMediaResponse(
        file_path,
        media_type=mime_type,
        headers=cache_headers,
        chunked=chunked,
        filename=download_filename,
        content_disposition_type=content_disposition_type
    )

def delete_media_cache(file_path: Path):
    """Delete the cached version of a media file if it exists."""
    try:
        if not file_path.exists():
            return
            
        import hashlib

        from ..config import settings
        
        stat = file_path.stat()
        cache_key = f"{str(file_path)}_{stat.st_mtime}"
        cache_filename = hashlib.md5(cache_key.encode()).hexdigest() + "_" + file_path.name
        cache_path = settings.CACHE_DIR / cache_filename
        
        if cache_path.exists():
            cache_path.unlink()
            logger.debug(f"Deleted cache file: {cache_path}")
            
    except Exception as e:
        logger.error(f"Error deleting media cache for {file_path}: {e}")

def cleanup_dead_media_cache(db) -> int:
    """Remove cache files that no longer correspond to any media in the database."""
    import hashlib
    
    from ..config import settings
    from ..models import Media
    
    if not settings.CACHE_DIR.exists():
        return 0
    
    base_dir = settings.BASE_DIR.resolve()
    
    # Build the set of cache filenames that are currently valid.
    # A cache entry is valid if the original file exists on disk; its
    # expected cache name is derived from the current mtime so we never
    # accidentally delete a freshly-queued entry.
    valid_names: set[str] = set()
    try:
        all_media = db.query(Media).filter(
            Media.mime_type.like("image/%")
        ).all()
    except Exception as e:
        logger.error(f"cleanup_dead_media_cache: DB query failed: {e}")
        return 0

    for media in all_media:
        try:
            raw_path = settings.BASE_DIR / media.path
            try:
                file_path = raw_path.resolve()
                if not file_path.is_relative_to(base_dir):
                    logger.warning(
                        f"cleanup_dead_media_cache: skipping out-of-tree path {media.path!r}"
                    )
                    continue
            except (ValueError, OSError):
                continue

            if not file_path.exists():
                continue

            stat = file_path.stat()
            cache_key = f"{str(file_path)}_{stat.st_mtime}"
            expected_name = hashlib.md5(cache_key.encode()).hexdigest() + "_" + file_path.name
            valid_names.add(expected_name)
        except Exception as e:
            logger.warning(f"cleanup_dead_media_cache: skipping media id={media.id}: {e}")

    deleted = 0
    try:
        for entry in settings.CACHE_DIR.iterdir():
            if entry.is_dir():
                continue
            # Leave in-progress atomic write temps alone
            if entry.suffix == ".tmp":
                continue
            # Only act on plain files; skip symlinks, sockets, etc.
            if not entry.is_file() or entry.is_symlink():
                continue
            if entry.name not in valid_names:
                try:
                    entry.unlink()
                    deleted += 1
                    logger.debug(f"Removed dead cache file: {entry.name}")
                except FileNotFoundError:
                    pass  # Already gone
                except Exception as unlink_err:
                    logger.error(f"Error removing dead cache file {entry}: {unlink_err}")
    except Exception as e:
        logger.error(f"cleanup_dead_media_cache: directory scan failed: {e}")

    if deleted:
        logger.info(
            f"Dead cache cleanup: removed {deleted} orphaned file(s) from {settings.CACHE_DIR}"
        )

    return deleted

def sanitize_filename(filename: str, fallback: str = "file") -> str:
    """Sanitize filename to be safe for filesystem and web."""
    import re
    
    path = Path(filename)
    stem = path.stem
    ext = path.suffix.lower()
    
    stem = re.sub(r'[^\w\s\-\.]', '_', stem)
    stem = re.sub(r'[\s_]+', '_', stem)
    stem = stem.strip('_')
    
    if not stem:
        stem = fallback
    
    return f"{stem}{ext}"

def get_unique_filename(directory: Path, filename: str) -> str:
    """Get a unique filename in the directory by appending a number if needed."""
    sanitized = sanitize_filename(filename)
    path = directory / sanitized
    
    if not path.exists():
        return sanitized
    
    # File exists, add a number suffix
    stem = Path(sanitized).stem
    ext = Path(sanitized).suffix
    counter = 1
    
    while True:
        new_filename = f"{stem}_{counter}{ext}"
        new_path = directory / new_filename
        if not new_path.exists():
            return new_filename
        counter += 1

def get_media_cache_status(file_path: Path, mime_type: str) -> str:
    """
    Check the status of the media cache file.
    Returns: 'ready', 'processing', or 'not_stripped'.
    """
    if not mime_type or not mime_type.startswith('image/'):
        return 'not_stripped'
        
    import hashlib

    from ..config import settings
    
    stat = file_path.stat()
    cache_key = f"{str(file_path)}_{stat.st_mtime}"
    cache_filename = hashlib.md5(cache_key.encode()).hexdigest() + "_" + file_path.name
    cache_path = settings.CACHE_DIR / cache_filename
    
    if cache_path.exists():
        return 'ready'
        
    return 'processing'
