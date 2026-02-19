from fastapi import HTTPException
from fastapi.responses import FileResponse
from PIL import Image
from pathlib import Path
import json
import mimetypes
from typing import Dict, Any, Optional
import cv2
import uuid

def extract_image_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract metadata from media files (EXIF, PNG chunks, XMP, etc.)"""
    metadata = {}
    mime_type, _ = mimetypes.guess_type(str(file_path))
    
    if not mime_type or not mime_type.startswith('image/'):
        return metadata
    
    try:
        with Image.open(file_path) as img:
            # Get PNG text chunks (ComfyUI, A1111, SwarmUI often use these)
            if hasattr(img, 'info') and img.info:
                for key, value in img.info.items():
                    if isinstance(value, str):
                        try:
                            metadata[key] = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            metadata[key] = value
                    elif isinstance(value, bytes):
                        try:
                            decoded = value.decode('utf-8', errors='ignore')
                            try:
                                metadata[key] = json.loads(decoded)
                            except (json.JSONDecodeError, ValueError):
                                metadata[key] = decoded
                        except Exception:
                            pass
                    else:
                        metadata[key] = value
            
            if hasattr(img, 'getexif'):
                exif = img.getexif()
                if exif:
                    # UserComment tag (0x9286) - often contains AI parameters
                    if 0x9286 in exif:
                        user_comment = exif[0x9286]
                        if isinstance(user_comment, bytes):
                            try:
                                user_comment = user_comment.decode('utf-8', errors='ignore')
                                user_comment = user_comment.replace('\x00', '').strip()
                            except Exception:
                                pass
                        
                        # Try to parse as JSON
                        if isinstance(user_comment, str) and user_comment:
                            try:
                                metadata['parameters'] = json.loads(user_comment)
                            except (json.JSONDecodeError, ValueError):
                                metadata['parameters'] = user_comment
                    
                    # ImageDescription tag (0x010E) - sometimes used for metadata
                    if 0x010E in exif:
                        description = exif[0x010E]
                        if isinstance(description, bytes):
                            try:
                                description = description.decode('utf-8', errors='ignore').replace('\x00', '').strip()
                            except Exception:
                                pass
                        
                        if isinstance(description, str) and description:
                            try:
                                parsed = json.loads(description)
                                if isinstance(parsed, dict):
                                    metadata.update(parsed)
                                else:
                                    metadata['description'] = parsed
                            except (json.JSONDecodeError, ValueError):
                                metadata['description'] = description
                    
                    # XPComment tag (0x9C9C) - Windows comment field
                    if 0x9C9C in exif:
                        xp_comment = exif[0x9C9C]
                        if isinstance(xp_comment, bytes):
                            try:
                                # XPComment is UTF-16LE encoded
                                decoded = xp_comment.decode('utf-16le', errors='ignore').replace('\x00', '').strip()
                                if decoded:
                                    try:
                                        metadata['parameters'] = json.loads(decoded)
                                    except (json.JSONDecodeError, ValueError):
                                        metadata['parameters'] = decoded
                            except Exception:
                                pass
                    
                    # XPKeywords tag (0x9C9E)
                    if 0x9C9E in exif:
                        xp_keywords = exif[0x9C9E]
                        if isinstance(xp_keywords, bytes):
                            try:
                                decoded = xp_keywords.decode('utf-16le', errors='ignore').replace('\x00', '').strip()
                                if decoded:
                                    try:
                                        metadata['keywords'] = json.loads(decoded)
                                    except (json.JSONDecodeError, ValueError):
                                        metadata['keywords'] = decoded
                            except Exception:
                                pass
            
            # For WebP specifically, try to get XMP data
            if img.format == 'WEBP' and hasattr(img, 'getxmp'):
                try:
                    xmp_data = img.getxmp()
                    if xmp_data:
                        metadata['xmp'] = xmp_data
                except Exception:
                    pass
            
            # Legacy EXIF method (for older PIL versions)
            if hasattr(img, '_getexif') and callable(img._getexif):
                try:
                    legacy_exif = img._getexif()
                    if legacy_exif and 0x9286 in legacy_exif:
                        user_comment = legacy_exif[0x9286]
                        if isinstance(user_comment, bytes):
                            user_comment = user_comment.decode('utf-8', errors='ignore').replace('\x00', '').strip()
                        if isinstance(user_comment, str) and user_comment and 'parameters' not in metadata:
                            try:
                                metadata['parameters'] = json.loads(user_comment)
                            except (json.JSONDecodeError, ValueError):
                                metadata['parameters'] = user_comment
                except Exception:
                    pass
        
        return metadata
        
    except Exception as e:
        print(f"Error reading metadata from {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return {}

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
        print(f"Error reading video metadata with cv2 for {file_path}: {e}")

    try:
        stat = file_path.stat()
        metadata['file_size'] = stat.st_size
        metadata['file_type'] = 'video'
        
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            metadata['mime_type'] = mime_type
            
    except Exception as e:
        print(f"Error getting video metadata for {file_path}: {e}")
    
    return metadata

def extract_media_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract metadata from any media file (image or video)."""
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type:
        if mime_type.startswith('image/'):
            return extract_image_metadata(file_path)
        elif mime_type.startswith('video/'):
            return extract_video_metadata(file_path)
    
    return {}

async def create_stripped_media_cache(file_path: Path, mime_type: str) -> Optional[Path]:
    """
    Create a metadata-stripped version of the media file in the cache.
    Returns the path to the cached file, or None if stripping is not supported/failed.
    """
    if not mime_type or not mime_type.startswith('image/'):
        return None
        
    import hashlib
    from ..config import settings
    from fastapi.concurrency import run_in_threadpool
    
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
            import io
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
                            duration_info = img.info.get('duration', None)
                            
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
                        print(f"Error extracting frame durations: {e}")
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
        print(f"Error stripping metadata from {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return None

async def serve_media_file(file_path: Path, mime_type: str, error_message: str = "File not found", strip_metadata: bool = False) -> FileResponse:
    """Serve a media file with error handling and optional metadata stripping."""
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=error_message)
    
    if not strip_metadata:
        return FileResponse(file_path, media_type=mime_type)
    
    if mime_type and mime_type.startswith('image/'):
        cache_path = await create_stripped_media_cache(file_path, mime_type)
        if cache_path:
            return FileResponse(cache_path, media_type=mime_type)
    
    # Fallback to original file if stripping not supported or failed
    return FileResponse(file_path, media_type=mime_type)

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
            print(f"Deleted cache file: {cache_path}")
            
    except Exception as e:
        print(f"Error deleting media cache for {file_path}: {e}")

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
