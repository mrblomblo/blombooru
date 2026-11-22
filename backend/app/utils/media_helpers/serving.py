from pathlib import Path
from typing import Any, Optional
from fastapi import HTTPException
from fastapi.responses import FileResponse
from .stripped_cache import create_stripped_media_cache, touch_cache_file

class ChunkedMediaResponse(FileResponse):
    """FileResponse subclass with Range request capping and optional video initial chunking."""
    MAX_RANGE_SIZE = 25 * 1024 * 1024       # 25 MB
    INITIAL_VIDEO_CHUNK = 2 * 1024 * 1024   # 2 MB

    def __init__(self, *args, chunked: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.chunked = chunked

    @staticmethod
    def _parse_range_header(http_range: str, file_size: int) -> list[tuple[int, int]]:
        from starlette.responses import FileResponse
        ranges = FileResponse._parse_range_header(http_range, file_size)
        
        capped_ranges = []
        for start, end in ranges:
            if end - start > ChunkedMediaResponse.MAX_RANGE_SIZE:
                end = start + ChunkedMediaResponse.MAX_RANGE_SIZE
            capped_ranges.append((start, end))
            
        return capped_ranges

    async def __call__(self, scope, receive, send) -> None:
        headers = dict(scope.get("headers", []))
        # Opt-in: inject a bounded initial range for videos to avoid connection starvation
        if self.chunked and b"range" not in headers:
            is_video = self.media_type and self.media_type.startswith("video/")
            if is_video:
                end_byte = self.INITIAL_VIDEO_CHUNK - 1
                scope["headers"].append((b"range", f"bytes=0-{end_byte}".encode()))
        await super().__call__(scope, receive, send)

async def serve_media_file(
    file_path: Path,
    mime_type: str,
    error_message: str = "File not found",
    strip_metadata: bool = False,
    chunked: bool = False,
    download: bool = False,
    filename: Optional[str] = None,
    media: Optional[Any] = None,
) -> FileResponse:
    """Serve a media file with error handling, optional metadata stripping, and browser caching."""
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=error_message)
    
    cache_headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    content_disposition_type = "attachment" if download else "inline"
    download_filename = filename or file_path.name if download else None
    
    if not strip_metadata:
        return ChunkedMediaResponse(
            file_path,
            media_type=mime_type,
            headers=cache_headers,
            chunked=chunked,
            filename=download_filename,
            content_disposition_type=content_disposition_type
        )
    
    if mime_type and mime_type.startswith('image/'):
        target = media if media is not None else file_path
        cache_path = await create_stripped_media_cache(target, mime_type)
        if cache_path:
            touch_cache_file(cache_path)
            return ChunkedMediaResponse(
                cache_path,
                media_type=mime_type,
                headers=cache_headers,
                chunked=chunked,
                filename=download_filename,
                content_disposition_type=content_disposition_type
            )
    
    # Fallback to file if stripping not supported or failed
    return ChunkedMediaResponse(
        file_path,
        media_type=mime_type,
        headers=cache_headers,
        chunked=chunked,
        filename=download_filename,
        content_disposition_type=content_disposition_type
    )
