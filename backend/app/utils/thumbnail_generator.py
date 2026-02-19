from pathlib import Path

import cv2
from PIL import Image

from ..schemas import FileTypeEnum

THUMBNAIL_SIZE = (300, 300)

def generate_image_thumbnail(source_path: Path, thumbnail_path: Path) -> bool:
    """Generate thumbnail for an image"""
    try:
        with Image.open(source_path) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            img.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
        return True
    except Exception as e:
        print(f"Error generating image thumbnail: {e}")
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
        img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        img.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
        return True
    except Exception as e:
        print(f"Error generating video thumbnail: {e}")
        return False

def generate_thumbnail(source_path: Path, thumbnail_path: Path, file_type: FileTypeEnum) -> bool:
    """Generate thumbnail based on file type"""
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    
    if file_type in [FileTypeEnum.image, FileTypeEnum.gif]:
        return generate_image_thumbnail(source_path, thumbnail_path)
    elif file_type == FileTypeEnum.video:
        return generate_video_thumbnail(source_path, thumbnail_path)
    
    return False
