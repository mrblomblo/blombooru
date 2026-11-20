## Admin: Media

> [!NOTE]
> Last updated: `November 20, 2026`

**Base path:** `/api/admin`

### Get media statistics

Requires a valid session.

```
GET /api/admin/media-stats
```

**Response:** `{ "total_media", "total_images", "total_gifs", "total_videos" }`

### Get comprehensive statistics

Requires a valid session.

```
GET /api/admin/stats
```

Returns an object with the following top-level keys:

- `media`: total count plus breakdowns by type and rating, and parent/child relationship counts
- `upload_trends`: daily upload counts for the past 30 days
- `tags`: total tags/aliases, top tags globally and per category, count per category
- `albums`: total count and size-bucket distribution
- `storage`: total bytes used and average file size

### Scan for untracked media

Requires `require_admin_mode`. Scans `ORIGINAL_DIR` for files not yet in the database.

```
POST /api/admin/scan-media
```

**Response:** `{ "new_files": 3, "files": ["/absolute/path/to/file.jpg", ...] }`

### Get untracked file metadata

Requires `require_admin_mode`. Returns lightweight metadata for a scanned file **without serving its binary content**.

```
GET /api/admin/get-untracked-file-info?path=/absolute/path/to/file.jpg
```

The path must be an absolute path inside `ORIGINAL_DIR`; requests for paths outside it are rejected with `403`.

**Response:** `{ "name": "file.jpg", "size": 8589934592, "mime_type": "video/mp4" }`

### Serve untracked file

Requires `require_admin_mode`. Streams the raw binary content of a scanned file to the client. Suitable for direct media previews (e.g. as a `<video src>` or `<img src>`).

```
GET /api/admin/get-untracked-file?path=/absolute/path/to/file.jpg
```

The path must be an absolute path inside `ORIGINAL_DIR`; requests for paths outside it are rejected with `403`.

### Regenerate all thumbnails

Requires `require_admin_mode`. Deletes every existing thumbnail and regenerates all of them from the original source files. Shares the media maintenance lock with thumbnail generation, relinking, and transcoding (`409` if another media maintenance job is running).

```
POST /api/admin/regenerate-all-thumbnails
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `background` | bool | `false` | When `true`, starts the job in the background (`regenerate_all_thumbnails`) instead of waiting for completion |

**Response (`background=false`):** `{ "deleted", "generated", "failed", "total" }`

**Response (`background=true`):** `{ "status": "started" | "already_running", "job": { ... } }`

### Generate missing thumbnails

Requires `require_admin_mode`. Removes orphaned thumbnail files and generates thumbnails only for media items that are missing one. Shares the media maintenance lock (`409` if another media maintenance job is running).

```
POST /api/admin/generate-missing-thumbnails
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `background` | bool | `false` | When `true`, starts the job in the background (`generate_missing_thumbnails`) instead of waiting for completion |

**Response (`background=false`):** `{ "orphans_deleted", "generated", "failed", "skipped", "total" }`

**Response (`background=true`):** `{ "status": "started" | "already_running", "job": { ... } }`

### Re-link media files

Requires `require_admin_mode`. Scans storage (`ORIGINAL_DIR`) and re-links database records for moved or renamed media files based on content hash. Also renames and moves corresponding transcoded files in `media/transcoded/` to maintain synchronization. Shares the media maintenance lock (`409` if another media maintenance job is running).

```
POST /api/admin/relink-media
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `background` | bool | `false` | When `true`, starts the job in the background (`relink_media`) instead of waiting for completion |

**Response (`background=false`):** `{ "relinked": 2, "unresolved": 0, "total_checked": 50, "details": [ { "id": 1, "old_path": "...", "new_path": "...", "filename": "..." } ] }`

**Response (`background=true`):** `{ "status": "started" | "already_running", "job": { ... } }`

### Transcode incompatible media

Requires `require_admin_mode`. Starts a background job to transcode media files with browser-incompatible codecs or containers into web-compatible formats. Shares the media maintenance lock (`409` if another media maintenance job is running).

```
POST /api/admin/transcode-media
```

**Response:** `{ "status": "started", "message": "Transcoding job started in background" }`

### Get media transcoding status

Requires `require_admin_mode`. Returns the current progress and last result of the background library transcoding job.

```
GET /api/admin/transcode-media/status
```

**Response:** `{ "running": false, "current": 0, "total": 0, "transcoded": 0, "already_transcoded": 0, "skipped": 0, "failed": 0, "current_file": null, "error": null, "last_result": null }`
