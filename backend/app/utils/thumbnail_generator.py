from pathlib import Path

import cv2
from PIL import Image

from ..schemas import FileTypeEnum
from .logger import logger
from . import image_plugins

THUMBNAIL_SIZE = (320, 320)
THUMBNAIL_EXT = ".webp"
THUMBNAIL_MIME = "image/webp"
THUMBNAIL_QUALITY = 80

def _save_thumbnail(img: Image.Image, thumbnail_path: Path) -> None:
    img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
    img.save(thumbnail_path, 'WEBP', quality=THUMBNAIL_QUALITY, method=6)

def generate_image_thumbnail(source_path: Path, thumbnail_path: Path) -> bool:
    """Generate thumbnail for an image"""
    try:
        with Image.open(source_path) as img:
            has_alpha = (
                img.mode in ('RGBA', 'LA', 'PA')
                or (img.mode == 'P' and 'transparency' in img.info)
                or 'transparency' in img.info
            )
            img = img.convert('RGBA' if has_alpha else 'RGB')
            _save_thumbnail(img, thumbnail_path)
        return True
    except Exception as e:
        logger.error(f"Error generating image thumbnail: {e}")
        return False

def generate_video_thumbnail(source_path: Path, thumbnail_path: Path) -> bool:
    """Generate thumbnail from first frame of video"""
    try:
        cap = cv2.VideoCapture(str(source_path))
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return False
        
        # Convert BGR to RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
        _save_thumbnail(img, thumbnail_path)
        return True
    except Exception as e:
        logger.error(f"Error generating video thumbnail: {e}")
        return False

def generate_thumbnail(source_path: Path, thumbnail_path: Path, file_type: FileTypeEnum) -> bool:
    """Generate thumbnail based on file type"""
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    
    if file_type in [FileTypeEnum.image, FileTypeEnum.gif]:
        return generate_image_thumbnail(source_path, thumbnail_path)
    elif file_type == FileTypeEnum.video:
        return generate_video_thumbnail(source_path, thumbnail_path)
    
    return False

def thumbnail_mime_type(path) -> str:
    """MIME type for a thumbnail file, tolerant of legacy .jpg thumbnails."""
    return "image/jpeg" if Path(path).suffix.lower() in (".jpg", ".jpeg") else THUMBNAIL_MIME
