from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from .types import ParsedMetadata

class MetadataParser(ABC):
    """Abstract base class for metadata parser backends."""

    name: str = "base"

    @classmethod
    @abstractmethod
    def can_handle(cls, media_path: Path, sibling_files: List[Path]) -> bool:
        """Fast check to determine if this parser can handle the media file or its sidecars."""
        ...

    @abstractmethod
    def parse(self, media_path: Path, sibling_files: List[Path]) -> ParsedMetadata:
        """Parse metadata from the media file or its sidecar files."""
        ...
