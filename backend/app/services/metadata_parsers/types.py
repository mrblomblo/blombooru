from dataclasses import dataclass, field
from typing import List, Optional

from ..booru.types import BooruTag

@dataclass
class ParsedMetadata:
    """Standardized metadata extracted from external sidecars or embedded tags."""
    tags: List[BooruTag] = field(default_factory=list)
    rating: Optional[str] = None  # Normalized to safe/questionable/explicit
    source: Optional[str] = None
    description: Optional[str] = None  # Artist commentary / notes
    pool_names: List[str] = field(default_factory=list)  # -> Proposed albums
    parent_source_id: Optional[str] = None  # For parent/child relations
    confidence: str = "sidecar"  # sidecar | exif | xmp | native
