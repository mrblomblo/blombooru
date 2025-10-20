from fastapi import HTTPException
from fastapi.responses import FileResponse
from PIL import Image
from pathlib import Path
import json
import mimetypes
from typing import Dict, Any, Optional

def extract_image_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract metadata from media files (EXIF, PNG chunks, XMP, etc.)"""
    metadata = {}
    
    # Check file type first
    mime_type, _ = mimetypes.guess_type(str(file_path))
    
    # Only process image files
    if not mime_type or not mime_type.startswith('image/'):
        # For video files or unknown types, return empty metadata
        # You could extend this to extract video metadata using ffprobe or similar
        return metadata
    
    try:
        with Image.open(file_path) as img:
            # Get PNG text chunks (ComfyUI, A1111, SwarmUI often use these)
            if hasattr(img, 'info') and img.info:
                for key, value in img.info.items():
                    # Store all text chunks
                    if isinstance(value, str):
                        # Try to parse as JSON first
                        try:
                            metadata[key] = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            # Store as string if not valid JSON
                            metadata[key] = value
                    elif isinstance(value, bytes):
                        # Handle byte strings
                        try:
                            decoded = value.decode('utf-8', errors='ignore')
                            try:
                                metadata[key] = json.loads(decoded)
                            except (json.JSONDecodeError, ValueError):
                                metadata[key] = decoded
                        except:
                            pass
                    else:
                        metadata[key] = value
            
            # Get EXIF data (for JPEG, WebP, etc.)
            if hasattr(img, 'getexif'):
                exif = img.getexif()
                if exif:
                    # UserComment tag (0x9286) - often contains AI parameters
                    if 0x9286 in exif:
                        user_comment = exif[0x9286]
                        # Handle bytes
                        if isinstance(user_comment, bytes):
                            try:
                                user_comment = user_comment.decode('utf-8', errors='ignore')
                                # Remove any null bytes or special characters
                                user_comment = user_comment.replace('\x00', '').strip()
                            except:
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
                            except:
                                pass
                        
                        if isinstance(description, str) and description:
                            try:
                                parsed = json.loads(description)
                                # Merge with metadata
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
                            except:
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
                            except:
                                pass
            
            # For WebP specifically, try to get XMP data
            if img.format == 'WEBP' and hasattr(img, 'getxmp'):
                try:
                    xmp_data = img.getxmp()
                    if xmp_data:
                        metadata['xmp'] = xmp_data
                except:
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
                except:
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
    
    # Todo: add proper video metadata extraction using:
    # - ffprobe (from ffmpeg)
    # - pymediainfo
    # - opencv-python

    try:
        stat = file_path.stat()
        metadata['file_size'] = stat.st_size
        metadata['file_type'] = 'video'
        
        # Try to get mime type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            metadata['mime_type'] = mime_type
            
    except Exception as e:
        print(f"Error getting video metadata for {file_path}: {e}")
    
    return metadata


def extract_media_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract metadata from any media file (image or video)."""
    # Determine file type
    mime_type, _ = mimetypes.guess_type(str(file_path))
    
    if mime_type:
        if mime_type.startswith('image/'):
            return extract_image_metadata(file_path)
        elif mime_type.startswith('video/'):
            return extract_video_metadata(file_path)
    
    # Unknown type, return empty metadata
    return {}


def serve_media_file(file_path: Path, mime_type: str, error_message: str = "File not found") -> FileResponse:
    """Serve a media file with error handling."""
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=error_message)
    
    return FileResponse(file_path, media_type=mime_type)


def sanitize_filename(filename: str, fallback: str = "file") -> str:
    """Sanitize filename to be safe for filesystem and web."""
    import re
    
    path = Path(filename)
    stem = path.stem
    ext = path.suffix.lower()
    
    # Replace problematic characters with underscores
    # Keep alphanumeric, spaces, hyphens, underscores, and dots
    stem = re.sub(r'[^\w\s\-\.]', '_', stem)
    # Replace multiple spaces/underscores with single underscore
    stem = re.sub(r'[\s_]+', '_', stem)
    # Remove leading/trailing underscores
    stem = stem.strip('_')
    
    # If stem is empty after sanitization, use the fallback
    if not stem:
        stem = fallback
    
    return f"{stem}{ext}"


def get_unique_filename(directory: Path, filename: str) -> str:
    """
    Get a unique filename in the directory by appending a number if needed.
    
    Args:
        directory: Directory to check for existing files
        filename: Desired filename (will be sanitized)
        
    Returns:
        Unique filename that doesn't exist in the directory
    """
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
