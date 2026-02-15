from typing import List, Optional
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

def get_client_for_url(url: str, db: Optional[Session] = None) -> Optional[BooruClient]:
    """
    Find the right BooruClient for a given URL by checking patterns.
    """
    for client_cls in _CLIENT_CLASSES:
        if client_cls.can_handle_url(url):
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            # Inject credentials if available
            if db:
                config = db.query(BooruConfig).filter(BooruConfig.domain == parsed.netloc).first()
                if config and config.username and config.api_key:
                    if client_cls == GelbooruClient:
                        return client_cls(base_url, user_id=config.username, api_key=config.api_key)
                    elif client_cls == DanbooruClient:
                        return client_cls(base_url, username=config.username, api_key=config.api_key)
                    else:
                         return client_cls(base_url)
            
            return client_cls(base_url)
    return None
