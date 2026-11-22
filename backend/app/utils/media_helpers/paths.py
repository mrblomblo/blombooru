from pathlib import Path
from typing import Any

def get_effective_media_path(media: Any) -> Path:
    """The file that actually backs a media's served/shared content."""
    from ...config import settings
    if getattr(media, "transcoded_path", None):
        return settings.BASE_DIR / media.transcoded_path
    if hasattr(media, "path"):
        return settings.BASE_DIR / media.path
    return Path(media)

def sanitize_filename(filename: str, fallback: str = "file", max_bytes: int = 240) -> str:
    """Sanitize filename to be safe for filesystem and web, truncating to prevent exceeding filesystem byte limits."""
    import re
    
    path = Path(filename)
    stem = path.stem
    ext = path.suffix.lower()[:32]
    
    stem = re.sub(r'[^\w\s\-\.]', '_', stem)
    stem = re.sub(r'[\s_]+', '_', stem)
    stem = stem.strip('_')
    
    if not stem:
        stem = fallback

    ext_bytes = len(ext.encode("utf-8"))
    max_stem_bytes = max(1, max_bytes - ext_bytes)
    stem_encoded = stem.encode("utf-8")
    if len(stem_encoded) > max_stem_bytes:
        stem = stem_encoded[:max_stem_bytes].decode("utf-8", errors="ignore").rstrip("_-.")
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
