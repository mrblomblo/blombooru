## Booru Import

> [!NOTE]
> Last updated: `May 31, 2026`

**Base path:** `/api/booru-import`

All endpoints require `require_admin_mode`.

Used to fetch metadata from and download media from external booru sites. Credentials for specific domains can be configured via the [Booru Config](/docs/Internal%20API/API/Booru%20Config.md) endpoints.

### Fetch post metadata

Retrieves tag, rating, and file information from a booru post URL without downloading the media file. Useful for previewing what will be imported.

```
POST /api/booru-import/fetch
Content-Type: application/json

{ "url": "https://danbooru.donmai.us/posts/12345" }
```

**Response:**

```json
{
  "id": 12345,
  "tags": [
    { "name": "fox", "category": "general", "is_new": false }
  ],
  "rating": "safe",
  "source": "https://example.com/original",
  "file_url": "https://cdn.example.com/img.jpg",
  "preview_url": "https://cdn.example.com/preview.jpg",
  "filename": "img.jpg",
  "width": 1920,
  "height": 1080,
  "file_size": 2048576,
  "score": 42,
  "booru_url": "https://danbooru.donmai.us/posts/12345"
}
```

`is_new` on each tag indicates whether that tag exists in the local database. Returns `400` for unsupported URLs, `403`/`404` from the remote booru, or `502` on API errors.

### Download and import post

Fetches metadata, downloads the media file, and imports it through the standard upload pipeline (hash deduplication, thumbnail generation, tagging).

```
POST /api/booru-import/download
Content-Type: application/json

{
  "url": "https://danbooru.donmai.us/posts/12345",
  "rating": "safe",
  "tags": ["fox", "landscape"],
  "source": "https://example.com",
  "album_ids": [1, 2],
  "auto_create_tags": false,
  "category_hints": { "fox": "general" }
}
```

All fields except `url` are optional. When `tags` is omitted, the tag list from the fetched post is used. When `auto_create_tags` is `true`, tags missing from the local database are created automatically using the category from the remote booru (or from `category_hints`).

**Response:** `MediaResponse`. Returns `409` if the file already exists (duplicate SHA-256 hash).

### Proxy image

Proxies an image request through the backend to bypass CORS. Used by the frontend to preview remote booru images.

```
GET /api/booru-import/proxy-image?url=<image-url>
```

Streams the remote image with a 1-hour cache header. Uses the stored booru credentials if a matching domain is configured. Returns `403`/`404` if the remote server rejects the request, or `502` on proxy failure.
