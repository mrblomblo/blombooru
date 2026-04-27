## Admin: Media

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

Returns an object with media counts by type/rating, upload trends (last 30 days), tag statistics, album size distribution, and storage usage.

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
