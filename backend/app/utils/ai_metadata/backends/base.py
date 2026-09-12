from abc import ABC, abstractmethod
from typing import Any, Dict

class AIMetadataBackend(ABC):
    """Abstract base class for AI generator metadata parser backends."""

    name: str = "Unknown"

    @abstractmethod
    def detect(self, raw_meta: Dict[str, Any]) -> bool:
        """Return True if this backend can parse the given raw metadata dictionary."""
        pass

    @abstractmethod
    def parse(self, raw_meta: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw metadata into the canonical AI metadata structure."""
        pass
