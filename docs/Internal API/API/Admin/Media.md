## Admin: Media

> [!NOTE]
> Last updated: `May 31, 2026`

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

- `media` -- total count plus breakdowns by type and rating, and parent/child relationship counts
- `upload_trends` -- daily upload counts for the past 30 days
- `tags` -- total tags/aliases, top tags globally and per category, count per category
- `albums` -- total count and size-bucket distribution
- `storage` -- total bytes used and average file size

### Scan for untracked media

Requires `require_admin_mode`. Scans `ORIGINAL_DIR` for files not yet in the database.

```
POST /api/admin/scan-media
```

**Response:** `{ "new_files": 3, "files": ["/absolute/path/to/file.jpg", ...] }`

### Serve untracked file

Requires `require_admin_mode`. Used to preview a scanned file before importing.

```
GET /api/admin/get-untracked-file?path=/absolute/path/to/file.jpg
```

The path must be an absolute path inside `ORIGINAL_DIR`; requests for paths outside it are rejected with `403`.

### Regenerate all thumbnails

Requires `require_admin_mode`. Deletes every existing thumbnail and regenerates all of them from the original source files.

```
POST /api/admin/regenerate-all-thumbnails
```

**Response:** `{ "deleted", "generated", "failed", "total" }`

### Generate missing thumbnails

Requires `require_admin_mode`. Removes orphaned thumbnail files and generates thumbnails only for media items that are missing one.

```
POST /api/admin/generate-missing-thumbnails
```

**Response:** `{ "orphans_deleted", "generated", "failed", "skipped", "total" }`
