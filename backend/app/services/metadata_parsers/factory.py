from pathlib import Path
from typing import Dict, List, Optional, Type

from ...config import settings
from .base import MetadataParser
from .exif_xmp import ExifXmpParser
from .gallery_dl import GalleryDlParser
from .lolisnatcher import LoliSnatcherParser

_PARSER_CLASSES: List[Type[MetadataParser]] = [
    GalleryDlParser,
    LoliSnatcherParser,
    ExifXmpParser,
]

_PARSER_MAP: Dict[str, Type[MetadataParser]] = {
    cls.__name__: cls for cls in _PARSER_CLASSES
}

_PARSER_MAP.update({
    "gallery_dl": GalleryDlParser,
    "gallery-dl": GalleryDlParser,
    "lolisnatcher": LoliSnatcherParser,
    "exif_xmp": ExifXmpParser,
    "exif": ExifXmpParser,
    "xmp": ExifXmpParser,
})

def get_configured_parsers() -> List[Type[MetadataParser]]:
    """Get active metadata parser classes sorted by configured priority."""
    cfg = settings.METADATA_PARSERS
    enabled_names = set(cfg.get("enabled", ["GalleryDlParser", "LoliSnatcherParser", "ExifXmpParser"]))
    priority_names = cfg.get("priority", ["GalleryDlParser", "LoliSnatcherParser", "ExifXmpParser"])

    sorted_classes: List[Type[MetadataParser]] = []
    seen: set[Type[MetadataParser]] = set()

    for name in priority_names:
        cls = _PARSER_MAP.get(name) or _PARSER_MAP.get(name.lower())
        if cls and cls not in seen and (cls.__name__ in enabled_names or name in enabled_names):
            sorted_classes.append(cls)
            seen.add(cls)

    # Add any remaining enabled classes not in priority list
    for name in enabled_names:
        cls = _PARSER_MAP.get(name) or _PARSER_MAP.get(name.lower())
        if cls and cls not in seen:
            sorted_classes.append(cls)
            seen.add(cls)

    return sorted_classes if sorted_classes else _PARSER_CLASSES

def get_parser_for_file(media_path: Path, sibling_files: List[Path]) -> Optional[MetadataParser]:
    """Find the highest-priority MetadataParser that can handle the given media file and its siblings."""
    for parser_cls in get_configured_parsers():
        if parser_cls.can_handle(media_path, sibling_files):
            return parser_cls()
    return None
