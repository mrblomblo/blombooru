## Media

> [!NOTE]
> Last updated: `September 8, 2026`

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

### MediaResponse Object

Every endpoint returning media records outputs a `MediaResponse`:

```json
{
  "id": 1,
  "filename": "20260908-image.webp",
  "path": "media/original/20260908-image.webp",
  "transcoded_path": "media/transcoded/20260908-image.webp",
  "thumbnail_path": "media/thumbnails/20260908-image.jpg",
  "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "file_type": "image",
  "mime_type": "image/webp",
  "file_size": 2048576,
  "width": 1920,
  "height": 1080,
  "duration": null,
  "rating": "safe",
  "source": "https://example.com/original",
  "description": "Artwork description text",
  "uploaded_at": "2026-09-08T18:00:00+00:00",
  "is_shared": false,
  "share_uuid": null,
  "share_language": null,
  "parent_id": null,
  "has_children": false,
  "tags": [ /* TagResponse[] */ ]
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

| Param | Type | Description |
|---|---|---|
| `chunked` | bool | Optional (default: `false`). When `true`, video responses without a `Range` header are limited to an initial 2MB chunk (for in-browser playback). |
| `download` | bool | Optional (default: `false`). When `true`, always serves the original uploaded file with `Content-Disposition: attachment; filename="..."`. When `false` (default for playback/preview), serves the transcoded version (e.g. `.mp4` for MKV/AVI, `.webp` for HEIC/JXL) if available. |

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
| `description` | string | No | Optional media description |
| `category_hints` | string | No | JSON object mapping tag names to category strings, e.g. `{"bob": "artist"}` |

If the uploaded file format requires transcoding (such as `.heic`, `.jxl`, `.mkv`, or `.avi`), the transcoded file is generated in `media/transcoded/` and used as the source for the thumbnail.

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

### Update post from source

Requires `require_admin_mode`. Allows selective updates to post metadata, tags, and replacement of the underlying media file via a remote URL.

```
PATCH /api/media/{id}/update-from-source
Content-Type: application/json

{
  "rating": "safe",
  "tags": ["tag1", "newtag"],
  "source": "https://...",
  "description": "Updated description",
  "filename": "new_name.jpg",
  "file_url": "https://example.com/new_image.jpg",
  "update_rating": true,
  "update_tags": true,
  "update_source": true,
  "update_description": true,
  "update_filename": false,
  "update_file": true,
  "merge_tags": true,
  "category_hints": { "newtag": "general" }
}
```

| Field | Type | Description |
|---|---|---|
| `update_rating` | bool | When `true`, updates the rating |
| `update_tags` | bool | When `true`, updates tags |
| `merge_tags` | bool | When `true` and `update_tags` is `true`, merges new tags into existing tags instead of replacing them |
| `update_source` | bool | When `true`, updates the source URL |
| `update_description` | bool | When `true`, updates the description |
| `update_filename` | bool | When `true`, renames the media file and transcoded file on disk |
| `update_file` | bool | When `true`, downloads the replacement file from `file_url`, recalculates hash, and regenerates transcoded media and thumbnails |

**Response:** Updated `MediaResponse`. Returns `409` if the replacement file is a duplicate of another post.

### Finalize post file update from device chunks

Requires `require_admin_mode`. Replaces an existing post's media file using chunks previously uploaded via `POST /api/media/upload-chunk`.

```
POST /api/media/{id}/update-file-finalize
Content-Type: application/x-www-form-urlencoded

upload_id=<uuid>&update_filename=false
```

| Field | Type | Description |
|---|---|---|
| `upload_id` | string | UUID of the completed chunked upload |
| `update_filename` | bool | Optional (default: `false`). When `true`, adopts the uploaded file's sanitized filename; when `false`, retains the post's current filename stem. |

Replaces the stored file, updates or creates transcoded media, regenerates thumbnails, and refreshes dimensions and metadata.

**Response:** Updated `MediaResponse`.

### Delete media

Requires `require_admin_mode`. Deletes the database record, original file, transcoded file (if present), and thumbnail from disk, purging corresponding caches.

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

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file | Yes | Chunk data (max 99 MB per chunk) |
| `upload_id` | string | No on chunk 0, Yes after | UUID identifying the session. Omit on the first chunk (`chunk_index == 0`) and the server will generate one; include the returned value on all subsequent chunks. |
| `chunk_index` | int | Yes | Zero-based chunk index |
| `total_chunks` | int | Yes | Total number of chunks |
| `filename` | string | Yes | Original filename |

`upload-chunk` response:

```json
{ "upload_id": "<server-assigned uuid>", "received": 0, "total": 4 }
```

The `upload_id` is present in every chunk response (not just the first) so callers can always retrieve it.

`upload-finalize` fields (multipart): `upload_id`, `rating`, `tags`, `album_ids`, `source`, `category_hints`, `description`. Transcoding is automatically applied if the file format requires it.

### Archive upload

For uploading `.zip`, `.tar`, or `.tar.gz` archives containing multiple media files:

```
POST   /api/media/archive-chunk               # Upload one archive chunk
POST   /api/media/extract-archive             # Reassemble and extract
GET    /api/media/archive-file/{upload_id}/{file_id}  # Fetch extracted file
DELETE /api/media/archive-cleanup/{upload_id} # Clean up session
```

`archive-chunk` follows the same server-assigned `upload_id` pattern as `upload-chunk` above.

`extract-archive` response:

```json
{
  "upload_id": "<uuid>",
  "files": [
    {
      "file_id": 0,
      "filename": "original_name.jpg",
      "mime_type": "image/jpeg",
      "url": "/api/media/archive-file/<uuid>/0"
    }
  ],
  "count": 1
}
```

Extracted files preserve their original filenames and can be inspected via the provided `url`.
