from pathlib import Path
from sqlalchemy.orm import Session
from ..models import Media
from ..config import settings
from .media_processor import calculate_file_hash
import uuid
import re

SUPPORTED_EXTENSIONS = {
    'image': ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'],
    'gif': ['.gif'],
    'video': ['.mp4', '.webm', '.mov', '.avi', '.mkv']
}

def is_supported_file(filename: str) -> bool:
    """Check if file extension is supported"""
    ext = Path(filename).suffix.lower()
    for extensions in SUPPORTED_EXTENSIONS.values():
        if ext in extensions:
            return True
    return False

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to be safe for filesystem and web"""
    # Get the stem and extension separately
    path = Path(filename)
    stem = path.stem
    ext = path.suffix
    
    stem = re.sub(r'[^\w\s\-\.]', '_', stem)
    stem = re.sub(r'[\s_]+', '_', stem)
    stem = stem.strip('_')
    
    if not stem:
        stem = str(uuid.uuid4())
    
    return f"{stem}{ext}"

def find_untracked_media(db: Session) -> dict:
    """Find untracked media files without processing them"""
    original_dir = settings.ORIGINAL_DIR
    untracked_files = []
    
    # Get all tracked files by multiple methods:
    # 1. File hashes (primary method)
    tracked_hashes = set()
    # 2. Absolute file paths (backup method)
    tracked_paths = set()
    # 3. Filenames
    tracked_filenames = set()
    
    all_media = db.query(Media).all()
    
    for media in all_media:
        if media.hash:
            tracked_hashes.add(media.hash)
        if media.filename:
            tracked_filenames.add(media.filename)
        if media.path:
            try:
                abs_path = (settings.BASE_DIR / media.path).resolve()
                tracked_paths.add(str(abs_path))
            except:
                pass
        
        if hasattr(media, 'original_path') and media.original_path:
            try:
                abs_path = Path(media.original_path).resolve()
                tracked_paths.add(str(abs_path))
            except:
                pass
    
    print(f"Scanning directory: {original_dir}")
    print(f"Tracked hashes: {len(tracked_hashes)}")
    print(f"Tracked paths: {len(tracked_paths)}")
    print(f"Tracked filenames: {len(tracked_filenames)}")
    
    for file_path in original_dir.rglob('*'):
        if file_path.is_symlink():
            continue
            
        if not file_path.is_file() or not is_supported_file(file_path.name):
            continue
        
        try:
            abs_path = str(file_path.resolve())
            
            if abs_path in tracked_paths:
                continue
            if file_path.name in tracked_filenames:
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
            print(f"Error checking file {file_path.name}: {str(e)}")
            continue
    
    print(f"Found {len(untracked_files)} untracked files")
    
    return {
        'new_files': len(untracked_files),
        'files': untracked_files
    }
