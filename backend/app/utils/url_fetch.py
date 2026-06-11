import mimetypes
import re
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

import requests

from ..enums import FileTypeEnum
from .media_processor import determine_file_type

SUPPORTED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "video/mp4",
    "video/webm",
}

DEFAULT_TIMEOUT = 60
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


class UrlFetchError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def validate_media_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UrlFetchError("admin.media_management.url_import.error_invalid_url")
    if not parsed.netloc:
        raise UrlFetchError("admin.media_management.url_import.error_invalid_url")
    return url.strip()


def _filename_from_content_disposition(header: Optional[str]) -> Optional[str]:
    if not header:
        return None
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', header, re.IGNORECASE)
    if match:
        return unquote(match.group(1).strip())
    return None


def _filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name
    if name:
        return name
    return "imported_media"


def _is_supported_media(mime_type: str, filename: str) -> bool:
    if mime_type in SUPPORTED_MIME_TYPES:
        return True
    if mime_type in ("application/octet-stream", "binary/octet-stream"):
        ext = Path(filename).suffix.lower()
        return ext in {
            ".jpg", ".jpeg", ".png", ".gif", ".webp",
            ".mp4", ".webm",
        }
    return False


def _request_headers(url: str) -> dict:
    parsed = urlparse(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"
    return {
        "User-Agent": "Blombooru/1.0 (url-import)",
        "Referer": referer,
    }


def probe_media_url(url: str) -> dict:
    """Probe a direct media URL and return metadata without downloading the full file."""
    url = validate_media_url(url)

    try:
        response = requests.head(
            url,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
            headers=_request_headers(url),
        )
        if response.status_code == 405 or response.status_code >= 500:
            response = requests.get(
                url,
                timeout=DEFAULT_TIMEOUT,
                allow_redirects=True,
                headers={**_request_headers(url), "Range": "bytes=0-0"},
                stream=True,
            )
    except requests.Timeout:
        raise UrlFetchError("admin.media_management.url_import.error_timeout", 504)
    except requests.ConnectionError:
        raise UrlFetchError("admin.media_management.url_import.error_connection", 502)
    except requests.RequestException as e:
        raise UrlFetchError(
            f"admin.media_management.url_import.error_request:::{str(e)}",
            502,
        )

    if response.status_code == 403:
        raise UrlFetchError("admin.media_management.url_import.error_access_denied", 403)
    if response.status_code == 404:
        raise UrlFetchError("admin.media_management.url_import.error_not_found", 404)
    if response.status_code >= 400:
        raise UrlFetchError(
            f"admin.media_management.url_import.error_http:::{response.status_code}",
            502,
        )

    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    filename = (
        _filename_from_content_disposition(response.headers.get("content-disposition"))
        or _filename_from_url(response.url or url)
    )

    if not content_type:
        guessed, _ = mimetypes.guess_type(filename)
        content_type = (guessed or "").lower()

    if not _is_supported_media(content_type, filename):
        raise UrlFetchError("admin.media_management.url_import.error_unsupported_type", 400)

    content_length = response.headers.get("content-length")
    file_size = int(content_length) if content_length and content_length.isdigit() else None
    if file_size is not None and file_size > MAX_DOWNLOAD_BYTES:
        raise UrlFetchError("admin.media_management.url_import.error_too_large", 400)

    file_type = determine_file_type(content_type, filename)
    is_video = file_type == FileTypeEnum.video

    return {
        "file_url": response.url or url,
        "filename": filename,
        "content_type": content_type,
        "file_size": file_size,
        "is_video": is_video,
    }


def fetch_media_stream(url: str) -> Tuple[requests.Response, str]:
    """Download a media URL as a streaming response. Caller must close the response."""
    url = validate_media_url(url)

    try:
        response = requests.get(
            url,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
            headers=_request_headers(url),
            stream=True,
        )
    except requests.Timeout:
        raise UrlFetchError("admin.media_management.url_import.error_timeout", 504)
    except requests.ConnectionError:
        raise UrlFetchError("admin.media_management.url_import.error_connection", 502)
    except requests.RequestException as e:
        raise UrlFetchError(
            f"admin.media_management.url_import.error_request:::{str(e)}",
            502,
        )

    if response.status_code == 403:
        response.close()
        raise UrlFetchError("admin.media_management.url_import.error_access_denied", 403)
    if response.status_code == 404:
        response.close()
        raise UrlFetchError("admin.media_management.url_import.error_not_found", 404)
    if response.status_code >= 400:
        status = response.status_code
        response.close()
        raise UrlFetchError(
            f"admin.media_management.url_import.error_http:::{status}",
            502,
        )

    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    filename = (
        _filename_from_content_disposition(response.headers.get("content-disposition"))
        or _filename_from_url(response.url or url)
    )

    if not content_type:
        guessed, _ = mimetypes.guess_type(filename)
        content_type = (guessed or "").lower()

    if not _is_supported_media(content_type, filename):
        response.close()
        raise UrlFetchError("admin.media_management.url_import.error_unsupported_type", 400)

    content_length = response.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_DOWNLOAD_BYTES:
        response.close()
        raise UrlFetchError("admin.media_management.url_import.error_too_large", 400)

    return response, content_type


def _filename_from_response(url: str, response: requests.Response) -> str:
    filename = (
        _filename_from_content_disposition(response.headers.get("content-disposition"))
        or _filename_from_url(response.url or url)
    )
    return filename


def download_media_to_temp(url: str) -> Tuple[Path, str]:
    """Download a media URL to a temporary file. Caller must move or delete the file."""
    response, _content_type = fetch_media_stream(url)
    filename = _filename_from_response(url, response)
    suffix = Path(filename).suffix or ".bin"

    tmp_path: Optional[Path] = None
    try:
        total_bytes = 0
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > MAX_DOWNLOAD_BYTES:
                    raise UrlFetchError("admin.media_management.url_import.error_too_large", 400)
                tmp.write(chunk)

        if total_bytes == 0:
            raise UrlFetchError("admin.media_management.url_import.error_empty_file", 400)

        return tmp_path, filename
    except Exception:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
    finally:
        response.close()
