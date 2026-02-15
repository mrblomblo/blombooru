from typing import List, Optional
from urllib.parse import urlparse

from .base import BooruClient
from .danbooru import DanbooruClient
from .gelbooru import GelbooruClient

_CLIENT_CLASSES = [
    DanbooruClient,
    GelbooruClient,
]

def get_client_for_url(url: str) -> Optional[BooruClient]:
    """
    Find the right BooruClient for a given URL by checking patterns.
    """
    for client_cls in _CLIENT_CLASSES:
        if client_cls.can_handle_url(url):
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            return client_cls(base_url)
    return None
