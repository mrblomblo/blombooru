from abc import ABC, abstractmethod
from typing import List

from .types import BooruPost

class BooruClient(ABC):
    """Abstract base for booru API clients."""

    @abstractmethod
    def fetch_post(self, post_id: int) -> BooruPost:
        """Fetch a single post by ID."""
        ...

    @abstractmethod
    def search_posts(self, tags: str = "", page: int = 1, limit: int = 20) -> List[BooruPost]:
        """Search posts by tags. Stub for future viewer feature."""
        ...

    @classmethod
    @abstractmethod
    def can_handle_url(cls, url: str) -> bool:
        """Check if this client class can handle the given URL pattern."""
        ...

    @abstractmethod
    def parse_post_id(self, url: str) -> int:
        """Extract post ID from a URL."""
        ...

    def fetch_post_by_url(self, url: str) -> BooruPost:
        """Convenience: parse URL and fetch post."""
        post_id = self.parse_post_id(url)
        return self.fetch_post(post_id)
