## Media

**Base path:** `/api/media`

### List media

```
GET /api/media
```

| Query param | Type | Description |
|---|---|---|
| `page` | int | Page number (default: 1) |
| `limit` | int | Items per page (default: from settings) |
| `rating` | string | Rating filter: `safe`, `questionable`, or `explicit` |
| `sort` | string | Sort field: `uploaded_at` (default), `filename`, `file_size`, `file_type` |
| `order` | string | `asc` or `desc` (default: `desc`) |

**Response:**

```json
{
  "items": [ /* MediaResponse[] */  ],
  "total": 1234,
  "page": 1,
  "pages": 13
}
```

### Get media item by ID

```
GET /api/media/{id}
```

Returns a `MediaResponse` extended with:

```json
{
  "hierarchy": [ /* MediaResponse[] - parent/siblings/children */ ],
  "share_ai_metadata": false
}
```

### Get multiple media items by ID (batch)

```
GET /api/media/batch?ids=1,2,3
```

| Query param | Type | Description |
|---|---|---|
| `ids` | string | Comma-separated media IDs |

**Response:** `{ "items": [ /* MediaResponse[] */ ] }`

### Serve media file

```
GET /api/media/{id}/file
```

Streams the original media file.

### Serve thumbnail

```
GET /api/media/{id}/thumbnail
```

Streams the JPEG thumbnail.

### Get file metadata (EXIF etc.)

```
GET /api/media/{id}/metadata
```

Returns extracted image metadata (EXIF, generation parameters for AI images, etc.).

### Get albums containing media

```
GET /api/media/{id}/albums
```

Returns `{ "albums": [ /* AlbumListResponse[] */ ] }`.

### Upload media

Requires `require_admin_mode`.

```
POST /api/media
Content-Type: multipart/form-data
```

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file | Yes* | The file to upload (*or use `scanned_path`) |
| `scanned_path` | string | Yes* | Absolute path to a file already inside `ORIGINAL_DIR` to import in-place |
| `rating` | string | No | `safe` (default), `questionable`, `explicit` |
| `tags` | string | No | Space-separated tag names |
| `album_ids` | string | No | Comma-separated album IDs |
| `source` | string | No | Source URL |
| `category_hints` | string | No | JSON object mapping tag names to category strings, e.g. `{"bob": "artist"}` |

**Response:** `MediaResponse`. Returns `409` if a duplicate (matching SHA-256 hash) already exists.

### Update media metadata

Requires `require_admin_mode`.

```
PATCH /api/media/{id}
Content-Type: application/json

{
  "rating": "safe",
  "tags": ["tag1", "tag2"],
  "source": "https://...",
  "description": "...",
  "parent_id": null
}
```

All fields are optional. Supplying `tags` replaces the tag list entirely. Setting `parent_id` to `null` clears the parent relationship.

**Response:** Updated `MediaResponse`.

### Delete media

Requires `require_admin_mode`. Deletes the database record and the original file and thumbnail from disk.

```
DELETE /api/media/{id}
```

**Response:** `{ "message": "Media deleted successfully" }`

### Share management

Requires `require_admin_mode`.

```
POST   /api/media/{id}/share           # Enable sharing (generates share UUID)
DELETE /api/media/{id}/share           # Disable sharing
PATCH  /api/media/{id}/share-settings  # Update share options
```

`PATCH /api/media/{id}/share-settings` body:

```json
{
  "share_ai_metadata": true,
  "share_language": "en"
}
```

`POST` response includes `{ "share_url": "/shared/<uuid>", "share_ai_metadata": false }`.

### Chunked upload (large files)

For files that would be too large to upload in a single request:

```
POST /api/media/upload-chunk          # Upload one chunk
POST /api/media/upload-finalize       # Reassemble and process
```

`upload-chunk` fields (multipart):

| Field | Type | Description |
|---|---|---|
| `file` | file | Chunk data (max 99 MB per chunk) |
| `upload_id` | string | UUID identifying the session |
| `chunk_index` | int | Zero-based chunk index |
| `total_chunks` | int | Total number of chunks |
| `filename` | string | Original filename |

`upload-finalize` fields (multipart): `upload_id`, `rating`, `tags`, `album_ids`, `source`, `category_hints` (same as regular upload).

### Archive upload

For uploading `.zip` or `.tar.gz` archives containing multiple media files:

```
POST   /api/media/archive-chunk               # Upload one archive chunk
POST   /api/media/extract-archive             # Reassemble and extract
GET    /api/media/archive-file/{upload_id}/{file_id}  # Fetch extracted file
DELETE /api/media/archive-cleanup/{upload_id} # Clean up session
```

`archive-chunk` and `extract-archive` use the same `upload_id` / `chunk_index` / `total_chunks` / `filename` pattern as chunked upload.

`extract-archive` response:

```json
{
  "upload_id": "<uuid>",
  "files": [
    { "file_id": 0, "filename": "img.jpg", "mime_type": "image/jpeg" }
  ],
  "count": 1
}
```

Each extracted file can then be imported individually using `POST /api/media` with `scanned_path`, or fetched by a client via `/api/media/archive-file/{upload_id}/{file_id}`.
