## Admin: Backup & Import

> [!NOTE]
> Last updated: `May 31, 2026`

**Base path:** `/api/admin`

All download endpoints require a valid session. The import endpoint requires `require_admin_mode`.

### Export tags as CSV

Downloads all tags and aliases as a CSV file in the same format accepted by the CSV importer.

```
GET /api/admin/backup/tags
```

**Response:** `text/csv` file download named `blombooru_tags.csv`.

### Export all media files

Downloads a ZIP archive containing every original media file.

```
GET /api/admin/backup/media
```

**Response:** `application/zip` file download named `blombooru_media_backup.zip`.

### Full backup

Downloads a ZIP archive that bundles all media files together with a `tags.csv` export and a `backup.json` file describing all media records and albums.

```
GET /api/admin/backup/full
```

**Response:** `application/zip` file download named `blombooru_full_backup.zip`.

The `backup.json` contains:

```json
{
  "version": "<app_version>",
  "schema_version": "<schema_version>",
  "type": "full_backup",
  "media": [
    {
      "filename": "img.jpg",
      "hash": "...",
      "file_type": "image",
      "mime_type": "image/jpeg",
      "file_size": 123456,
      "width": 1920,
      "height": 1080,
      "duration": null,
      "rating": "safe",
      "tags": ["fox", "landscape"],
      "archive_path": "media/img.jpg",
      "parent_hash": null
    }
  ],
  "albums": [
    {
      "id": 1,
      "name": "My Album",
      "created_at": "...",
      "last_modified": "...",
      "media_hashes": ["abc123"],
      "child_ids": []
    }
  ]
}
```

### Import a full backup

Requires `require_admin_mode`. Accepts the ZIP file produced by the full backup endpoint.

```
POST /api/admin/import/full
Content-Type: multipart/form-data

file=<zip-file>
```

**Response:** An object summarising what was imported (tags, aliases, media, albums created/skipped).
