## URL Import

> [!NOTE]
> Last updated: `September 8, 2026`

**Base path:** `/api/media/url-import`

All endpoints require `require_admin_mode`.

The URL Import API provides a unified service for probing, proxying, and importing media from remote URLs. It automatically differentiates between direct media URLs and supported external booru posts (such as Danbooru, Gelbooru, and Moebooru), extracting metadata and downloading media in a single workflow.

---

### Probe / Fetch media URL

Probes a remote URL without downloading the full file. Automatically detects whether the URL is an external booru post or a direct media link.

```
POST /api/media/url-import/fetch
Content-Type: application/json

{
  "url": "https://danbooru.donmai.us/posts/12345"
}
```

**Response (Booru post URL):**

```json
{
  "is_booru_post": true,
  "id": 12345,
  "tags": [
    { "name": "fox", "category": "general", "is_new": false }
  ],
  "rating": "safe",
  "source": "https://example.com/art.jpg",
  "file_url": "https://cdn.example.com/art.jpg",
  "preview_url": "https://cdn.example.com/preview.jpg",
  "filename": "art.jpg",
  "width": 1920,
  "height": 1080,
  "file_size": 2048576,
  "score": 42,
  "booru_url": "https://danbooru.donmai.us/posts/12345",
  "description": "Artist commentary"
}
```

**Response (Direct media URL):**

```json
{
  "is_booru_post": false,
  "filename": "photo.webp",
  "mime_type": "image/webp",
  "file_size": 1048576
}
```

---

### Proxy media stream

Proxies a remote media file through the backend to bypass browser CORS restrictions. Streams binary content with `Cache-Control: no-store`.

```
GET /api/media/url-import/proxy?url=<encoded-media-url>
```

---

### Import media from URL

Downloads media from a direct URL or an external booru URL and imports it directly into the library through the standard pipeline (hash deduplication, transcoding if needed, thumbnail generation, tag and album linking).

```
POST /api/media/url-import/import
Content-Type: application/json

{
  "url": "https://danbooru.donmai.us/posts/12345",
  "rating": "safe",
  "tags": ["fox", "forest"],
  "source": "https://example.com/source",
  "album_ids": [1],
  "auto_create_tags": true,
  "category_hints": { "fox": "character" }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | Yes | Remote media URL or supported booru post URL |
| `rating` | string | No | Optional rating override (`safe`, `questionable`, `explicit`). If omitted on a booru post, uses the booru post rating (defaulting to `safe`). |
| `tags` | string[] | No | Optional list of tag names. If omitted on a booru post, uses the tags from the booru. |
| `source` | string | No | Optional source URL. If omitted on a booru post, uses the booru post source or post page URL. |
| `album_ids` | int[] | No | Optional album IDs to link the imported post to |
| `category_hints` | object | No | JSON object mapping tag names to categories |
| `auto_create_tags` | bool | No | Optional (default: `false`). When `true` on a booru import, tags missing from the local database are created using categories from the remote booru. |

When importing from a booru post, descriptions and filenames are automatically extracted from the remote post unless overridden.

**Response:** `MediaResponse`. Returns `409 Conflict` if the file hash already exists in the library.
