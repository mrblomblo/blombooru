import hashlib
from pathlib import Path
from PIL import Image
import cv2
import magic
from typing import Tuple, Optional
from ..schemas import FileTypeEnum

def calculate_file_hash(file_path: Path) -> str:
    """Calculate MD5 hash of a file"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_mime_type(file_path: Path) -> str:
    """Get MIME type of a file"""
    mime = magic.Magic(mime=True)
    return mime.from_file(str(file_path))

def determine_file_type(mime_type: str, filename: str, file_path: Path = None) -> FileTypeEnum:
    """Determine if file is image, video, or gif"""
    if mime_type.startswith('video/'):
        return FileTypeEnum.video
    elif mime_type == 'image/gif':
        return FileTypeEnum.gif
    elif mime_type == 'image/webp':
        # Check if WebP is animated
        if file_path and is_animated_webp(file_path):
            return FileTypeEnum.gif
        else:
            return FileTypeEnum.image
    elif mime_type.startswith('image/'):
        return FileTypeEnum.image
    else:
        # Fallback to extension
        ext = filename.lower().split('.')[-1]
        if ext in ['mp4', 'webm', 'mov', 'avi', 'mkv']:
            return FileTypeEnum.video
        elif ext == 'gif':
            return FileTypeEnum.gif
        elif ext == 'webp' and file_path and is_animated_webp(file_path):
            return FileTypeEnum.gif
        else:
            return FileTypeEnum.image

def is_animated_webp(file_path: Path) -> bool:
    """Check if a WebP file is animated by looking for the ANIM chunk"""
    try:
        with open(file_path, 'rb') as f:
            # Read first 12 bytes to check RIFF header
            header = f.read(12)
            if len(header) < 12:
                return False
            
            # Check for RIFF and WEBP signature
            if header[0:4] != b'RIFF' or header[8:12] != b'WEBP':
                return False
            
            # Read the rest of the file to look for ANIM chunk
            # ANIM chunk should be early in the file
            chunk_data = f.read(1024)  # Read first 1KB after header
            
            # Look for 'ANIM' chunk marker
            return b'ANIM' in chunk_data
    except Exception as e:
        print(f"Error checking if WebP is animated: {e}")
        return False

def get_image_dimensions(file_path: Path) -> Optional[Tuple[int, int]]:
    """Get dimensions of an image"""
    try:
        with Image.open(file_path) as img:
            return img.size
    except Exception:
        return None

def get_video_info(file_path: Path) -> Optional[dict]:
    """Get video dimensions and duration"""
    try:
        cap = cv2.VideoCapture(str(file_path))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        cap.release()
        
        return {
            'width': width,
            'height': height,
            'duration': duration
        }
    except Exception:
        return None

def process_media_file(file_path: Path) -> dict:
    """Process media file and extract metadata"""
    file_size = file_path.stat().st_size
    file_hash = calculate_file_hash(file_path)
    mime_type = get_mime_type(file_path)
    file_type = determine_file_type(mime_type, file_path.name, file_path)
    
    result = {
        'hash': file_hash,
        'mime_type': mime_type,
        'file_type': file_type,
        'file_size': file_size,
        'width': None,
        'height': None,
        'duration': None
    }
    
    if file_type in [FileTypeEnum.image, FileTypeEnum.gif]:
        dimensions = get_image_dimensions(file_path)
        if dimensions:
            result['width'], result['height'] = dimensions
    elif file_type == FileTypeEnum.video:
        video_info = get_video_info(file_path)
        if video_info:
            result.update(video_info)
    
    return result
