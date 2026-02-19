import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import requests

from .base import BooruClient
from .types import BooruPost, BooruTag

GELBOORU_RATING_MAP: Dict[str, str] = {
    "safe": "safe",
    "questionable": "questionable",
    "explicit": "explicit",
    "s": "safe",
    "q": "questionable",
    "e": "explicit",
}

class GelbooruClient(BooruClient):
    """
    Client for Gelbooru v0.2 style APIs (index.php?page=dapi...).
    Used by Gelbooru, Safebooru (classic), and many others.
    """

    MAX_RETRIES = 2
    RETRY_DELAY = 1.0

    def __init__(self, base_url: str, api_key: Optional[str] = None, user_id: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Blombooru/1.0 (booru-import)",
            "Accept": "application/json",
        })
        if api_key and user_id:
            self.session.params = {"api_key": api_key, "user_id": user_id}

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        """
        Check if the URL looks like a Gelbooru/Moebooru post URL.
        Typically: index.php?page=post&s=view&id=...
        """
        parsed = urlparse(url.lower())
        if "index.php" not in parsed.path:
            return False
        
        qs = parse_qs(parsed.query)
        return (
            qs.get("page") == ["post"] and
            qs.get("s") == ["view"] and
            "id" in qs
        )

    def parse_post_id(self, url: str) -> int:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "id" not in qs:
            raise ValueError(f"Could not extract post ID from URL: {url}")
        return int(qs["id"][0])

    def _request_with_retry(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make a GET request with basic retry/backoff for rate limits."""
        last_error = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = self.session.get(url, params=params, timeout=15)
                
                if response.status_code == 429:
                    # Back off when rate-limited
                    if attempt < self.MAX_RETRIES:
                        time.sleep(self.RETRY_DELAY * (attempt + 1))
                        continue
                    raise Exception("Rate limited by booru API")

                if response.status_code == 404:
                    raise Exception("Post not found")

                response.raise_for_status()

                if not response.text.strip():
                    raise Exception("Empty response from API")

                data = response.json()
                if isinstance(data, list):
                    if not data:
                        return [] 
                    return data
                elif isinstance(data, dict) and "post" in data:
                    return data["post"]
                
                return data

            except requests.RequestException as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                    continue

        raise Exception(f"Failed to fetch from booru after {self.MAX_RETRIES + 1} attempts: {last_error}")

    def _parse_tags_from_post(self, data: dict) -> List[BooruTag]:
        """
        Parse tags from a Gelbooru post response.
        Gelbooru returns tags as a space-separated string in the 'tags' field.
        Categories are not typically provided in the post object.
        """
        tags = []
        tag_string = data.get("tags", "")
        
        if tag_string:
            for tag_name in tag_string.split():
                tag_name = tag_name.strip()
                if tag_name:
                    tags.append(BooruTag(name=tag_name, category="general"))
        
        return tags

    def _map_rating(self, rating: Optional[str]) -> str:
        """Map Gelbooru rating to Blombooru rating."""
        if not rating:
            return "safe"
        return GELBOORU_RATING_MAP.get(rating.lower(), "safe")

    def _get_filename(self, data: dict) -> str:
        """Extract filename from post data."""
        filename = data.get("image")
        if filename:
            return filename
        
        file_url = data.get("file_url")
        if file_url:
            path = urlparse(file_url).path
            return path.split("/")[-1] if "/" in path else f"gelbooru_{data.get('id', 'unknown')}"

        return f"gelbooru_{data.get('id', 'unknown')}"

    def fetch_post(self, post_id: int) -> BooruPost:
        url = f"{self.base_url}/index.php"
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": "1",
            "id": post_id
        }

        data_list = self._request_with_retry(url, params=params)
        if not data_list:
            raise Exception("Post not found")
        
        if isinstance(data_list, list):
            data = data_list[0]
        else:
            data = data_list

        tags = self._parse_tags_from_post(data)
        rating = self._map_rating(data.get("rating"))
        source = data.get("source", "") or ""

        file_url = data.get("file_url") or data.get("image")
        
        # Handle relative URLs
        if file_url and not file_url.startswith("http"):
            if file_url.startswith("/"):
                file_url = f"{self.base_url}{file_url}"
            else:
                file_url = f"{self.base_url}/{file_url}"

        preview_url = data.get("preview_url")
        if preview_url and not preview_url.startswith("http"):
            if preview_url.startswith("/"):
                preview_url = f"{self.base_url}{preview_url}"
            else:
                preview_url = f"{self.base_url}/{preview_url}"

        return BooruPost(
            id=data.get("id", post_id),
            tags=tags,
            rating=rating,
            source=source,
            file_url=file_url,
            preview_url=preview_url,
            filename=self._get_filename(data),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            file_size=0,
            score=int(data.get("score") or 0),
            booru_url=f"{self.base_url}/index.php?page=post&s=view&id={data.get('id', post_id)}",
        )

    def search_posts(self, tags: str = "", page: int = 1, limit: int = 20) -> List[BooruPost]:
        """Search posts by tags."""
        url = f"{self.base_url}/index.php"
        params = {
            "page": "dapi", 
            "s": "post", 
            "q": "index", 
            "json": "1", 
            "tags": tags, 
            "pid": page - 1, # Gelbooru uses 0-indexed page (pid)
            "limit": min(limit, 100)
        }

        posts_data = self._request_with_retry(url, params=params)
        
        if not posts_data:
            return []

        results = []
        for data in posts_data:
            try:
                tags_list = self._parse_tags_from_post(data)
                
                file_url = data.get("file_url") or data.get("image")
                if file_url and not file_url.startswith("http"):
                    if file_url.startswith("/"):
                        file_url = f"{self.base_url}{file_url}"
                    else:
                        file_url = f"{self.base_url}/{file_url}"

                preview_url = data.get("preview_url")
                if preview_url and not preview_url.startswith("http"):
                    if preview_url.startswith("/"):
                        preview_url = f"{self.base_url}{preview_url}"
                    else:
                        preview_url = f"{self.base_url}/{preview_url}"

                post = BooruPost(
                    id=data.get("id", 0),
                    tags=tags_list,
                    rating=self._map_rating(data.get("rating")),
                    source=data.get("source", "") or "",
                    file_url=file_url,
                    preview_url=preview_url,
                    filename=self._get_filename(data),
                    width=int(data.get("width") or 0),
                    height=int(data.get("height") or 0),
                    file_size=0,
                    score=int(data.get("score") or 0),
                    booru_url=f"{self.base_url}/index.php?page=post&s=view&id={data.get('id', 0)}",
                )
                results.append(post)
            except Exception as e:
                print(f"Error parsing booru post {data.get('id')}: {e}")
                continue

        return results
