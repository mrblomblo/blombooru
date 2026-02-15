import re
import time
import requests
from typing import List, Optional, Dict
from urllib.parse import urlparse

from .base import BooruClient
from .types import BooruPost, BooruTag

DANBOORU_CATEGORY_MAP: Dict[int, str] = {
    0: "general",
    1: "artist",
    3: "copyright",
    4: "character",
    5: "meta",
}

DANBOORU_RATING_MAP: Dict[str, str] = {
    "g": "safe",
    "s": "safe",
    "q": "questionable",
    "e": "explicit",
}

class DanbooruClient(BooruClient):
    """
    Client for Danbooru-style APIs.
    """

    POST_URL_PATTERN = re.compile(r"/posts/(\d+)")
    MAX_RETRIES = 2
    RETRY_DELAY = 1.0  # seconds

    def __init__(self, base_url: str, api_key: Optional[str] = None, username: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.username = username
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Blombooru/1.0 (booru-import)",
            "Accept": "application/json",
        })
        if api_key and username:
            self.session.params = {"api_key": api_key, "login": username}

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        """Check if the URL looks like a Danbooru-style post URL."""
        parsed = urlparse(url)
        return bool(cls.POST_URL_PATTERN.search(parsed.path))

    def parse_post_id(self, url: str) -> int:
        match = self.POST_URL_PATTERN.search(url)
        if not match:
            raise ValueError(f"Could not extract post ID from URL: {url}")
        return int(match.group(1))

    def _request_with_retry(self, url: str) -> dict:
        """Make a GET request with basic retry/backoff for rate limits."""
        last_error = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = self.session.get(url, timeout=15)

                if response.status_code == 429:
                    # Back off when rate-limited
                    if attempt < self.MAX_RETRIES:
                        time.sleep(self.RETRY_DELAY * (attempt + 1))
                        continue
                    raise Exception("Rate limited by booru API")

                if response.status_code == 404:
                    raise Exception("Post not found")

                response.raise_for_status()
                return response.json()

            except requests.RequestException as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                    continue

        raise Exception(f"Failed to fetch from booru after {self.MAX_RETRIES + 1} attempts: {last_error}")

    def _parse_tags_from_post(self, data: dict) -> List[BooruTag]:
        """
        Parse tags from a Danbooru post response.
        
        Danbooru returns tags as space-separated strings per category:
        tag_string_general, tag_string_artist, tag_string_character,
        tag_string_copyright, tag_string_meta
        """
        tags = []
        category_fields = {
            "tag_string_general": "general",
            "tag_string_artist": "artist",
            "tag_string_character": "character",
            "tag_string_copyright": "copyright",
            "tag_string_meta": "meta",
        }

        for field_name, category in category_fields.items():
            tag_string = data.get(field_name, "")
            if tag_string:
                for tag_name in tag_string.split():
                    tag_name = tag_name.strip()
                    if tag_name:
                        tags.append(BooruTag(name=tag_name, category=category))

        if not tags and data.get("tag_string"):
            for tag_name in data["tag_string"].split():
                tag_name = tag_name.strip()
                if tag_name:
                    tags.append(BooruTag(name=tag_name, category="general"))

        return tags

    def _map_rating(self, rating: Optional[str]) -> str:
        """Map Danbooru rating to Blombooru rating."""
        if not rating:
            return "safe"
        return DANBOORU_RATING_MAP.get(rating.lower(), "safe")

    def _get_filename(self, data: dict) -> str:
        """Extract filename from post data."""
        md5 = data.get("md5", "")
        ext = data.get("file_ext", "")
        if md5 and ext:
            return f"{md5}.{ext}"

        file_url = data.get("file_url") or data.get("large_file_url", "")
        if file_url:
            path = urlparse(file_url).path
            return path.split("/")[-1] if "/" in path else f"booru_{data.get('id', 'unknown')}"

        return f"booru_{data.get('id', 'unknown')}"

    def fetch_post(self, post_id: int) -> BooruPost:
        url = f"{self.base_url}/posts/{post_id}.json"
        data = self._request_with_retry(url)

        tags = self._parse_tags_from_post(data)
        rating = self._map_rating(data.get("rating"))
        source = data.get("source", "") or ""

        file_url = data.get("file_url") or data.get("large_file_url")
        preview_url = data.get("preview_file_url") or data.get("large_file_url")

        return BooruPost(
            id=data.get("id", post_id),
            tags=tags,
            rating=rating,
            source=source,
            file_url=file_url,
            preview_url=preview_url,
            filename=self._get_filename(data),
            width=data.get("image_width", 0),
            height=data.get("image_height", 0),
            file_size=data.get("file_size", 0),
            score=data.get("score", 0),
            booru_url=f"{self.base_url}/posts/{data.get('id', post_id)}",
        )

    def search_posts(self, tags: str = "", page: int = 1, limit: int = 20) -> List[BooruPost]:
        """Search posts by tags. ready for future viewer feature."""
        url = f"{self.base_url}/posts.json"
        params = {"tags": tags, "page": page, "limit": min(limit, 200)}

        response = self.session.get(url, params=params, timeout=15)
        response.raise_for_status()
        posts_data = response.json()

        results = []
        for data in posts_data:
            try:
                tags_list = self._parse_tags_from_post(data)
                post = BooruPost(
                    id=data.get("id", 0),
                    tags=tags_list,
                    rating=self._map_rating(data.get("rating")),
                    source=data.get("source", "") or "",
                    file_url=data.get("file_url") or data.get("large_file_url"),
                    preview_url=data.get("preview_file_url") or data.get("large_file_url"),
                    filename=self._get_filename(data),
                    width=data.get("image_width", 0),
                    height=data.get("image_height", 0),
                    file_size=data.get("file_size", 0),
                    score=data.get("score", 0),
                    booru_url=f"{self.base_url}/posts/{data.get('id', 0)}",
                )
                results.append(post)
            except Exception as e:
                print(f"Error parsing booru post {data.get('id')}: {e}")
                continue

        return results
