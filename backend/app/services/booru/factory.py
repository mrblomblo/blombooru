from threading import Lock
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ...models import BooruConfig
from .base import BooruClient
from .danbooru import DanbooruClient
from .gelbooru import GelbooruClient

_CLIENT_CLASSES = [
    DanbooruClient,
    GelbooruClient,
]

_client_cache: Dict[Tuple, BooruClient] = {}
_cache_lock = Lock()

def get_client_for_url(url: str, db: Optional[Session] = None) -> Optional[BooruClient]:
    """Find the right BooruClient for a given URL by checking patterns."""
    for client_cls in _CLIENT_CLASSES:
        if client_cls.can_handle_url(url):
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            username: Optional[str] = None
            api_key: Optional[str] = None

            # Inject credentials if available
            if db:
                config = db.query(BooruConfig).filter(BooruConfig.domain == parsed.netloc).first()
                if config and config.username and config.api_key:
                    username = config.username
                    api_key = config.api_key

            cache_key = (client_cls, base_url, username, api_key)

            with _cache_lock:
                if cache_key not in _client_cache:
                    if username and api_key:
                        if client_cls == GelbooruClient:
                            client = client_cls(base_url, user_id=username, api_key=api_key)
                        elif client_cls == DanbooruClient:
                            client = client_cls(base_url, username=username, api_key=api_key)
                        else:
                            client = client_cls(base_url)
                    else:
                        client = client_cls(base_url)
                    _client_cache[cache_key] = client

                return _client_cache[cache_key]
    return None
