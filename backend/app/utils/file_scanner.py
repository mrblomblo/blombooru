from pathlib import Path
from sqlalchemy.orm import Session
from ..models import Media
from ..config import settings
from .media_processor import process_media_file, calculate_file_hash
from .thumbnail_generator import generate_thumbnail
import uuid
import shutil

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

def scan_for_new_media(db: Session) -> dict:
    """Scan original directory for untracked media files"""
    original_dir = settings.ORIGINAL_DIR
    new_files = []
    errors = []
    
    # Get all tracked file hashes
    tracked_hashes = {m.hash for m in db.query(Media.hash).all()}
    
    print(f"Scanning directory: {original_dir}")
    print(f"Tracked hashes: {len(tracked_hashes)}")
    
    # Scan directory
    for file_path in original_dir.rglob('*'):
        if not file_path.is_file() or not is_supported_file(file_path.name):
            continue
        
        try:
            # Check if already tracked
            file_hash = calculate_file_hash(file_path)
            if file_hash in tracked_hashes:
                continue
            
            print(f"Processing new file: {file_path.name}")
            
            # Process new file
            metadata = process_media_file(file_path)
            
            # Generate a UUID for this media
            media_uuid = str(uuid.uuid4())
            
            # Get the original file extension
            original_extension = file_path.suffix
            
            # Create new filename with UUID
            new_filename = f"{media_uuid}{original_extension}"
            new_file_path = file_path.parent / new_filename
            
            # Rename the original file
            try:
                shutil.move(str(file_path), str(new_file_path))
                print(f"Renamed {file_path.name} to {new_filename}")
            except Exception as e:
                error_msg = f"{file_path.name}: Failed to rename - {str(e)}"
                errors.append(error_msg)
                print(f"Error renaming file: {error_msg}")
                continue
            
            # Generate thumbnail
            thumbnail_filename = f"{media_uuid}.jpg"
            thumbnail_path = settings.THUMBNAIL_DIR / thumbnail_filename
            
            thumbnail_generated = generate_thumbnail(
                new_file_path,
                thumbnail_path,
                metadata['file_type']
            )
            
            # Create media record
            relative_path = new_file_path.relative_to(settings.BASE_DIR)
            relative_thumb = thumbnail_path.relative_to(settings.BASE_DIR) if thumbnail_generated else None
            
            media = Media(
                filename=new_filename,
                path=str(relative_path),
                thumbnail_path=str(relative_thumb) if relative_thumb else None,
                hash=metadata['hash'],
                file_type=metadata['file_type'],
                mime_type=metadata['mime_type'],
                file_size=metadata['file_size'],
                width=metadata['width'],
                height=metadata['height'],
                duration=metadata['duration']
            )
            
            db.add(media)
            new_files.append(new_filename)
            tracked_hashes.add(file_hash)
            
            print(f"Added to database: {new_filename}")
            
        except Exception as e:
            error_msg = f"{file_path.name}: {str(e)}"
            errors.append(error_msg)
            print(f"Error processing file: {error_msg}")
    
    if new_files:
        db.commit()
        print(f"Committed {len(new_files)} new files to database")
    
    return {
        'new_files': len(new_files),
        'files': new_files,
        'errors': errors
    }
    
def find_untracked_media(db: Session) -> dict:
    """Find untracked media files without processing them"""
    original_dir = settings.ORIGINAL_DIR
    untracked_files = []
    
    # Get all tracked file hashes
    tracked_hashes = {m.hash for m in db.query(Media.hash).all()}
    
    print(f"Scanning directory: {original_dir}")
    print(f"Tracked hashes: {len(tracked_hashes)}")
    
    # Scan directory
    for file_path in original_dir.rglob('*'):
        if not file_path.is_file() or not is_supported_file(file_path.name):
            continue
        
        try:
            # Check if already tracked
            file_hash = calculate_file_hash(file_path)
            if file_hash in tracked_hashes:
                continue
            
            # Add to untracked list with full path
            untracked_files.append({
                'path': str(file_path),
                'filename': file_path.name,
                'hash': file_hash
            })
            
        except Exception as e:
            print(f"Error checking file {file_path.name}: {str(e)}")
            continue
    
    return {
        'new_files': len(untracked_files),
        'files': untracked_files
    }
