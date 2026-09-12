## Admin: Backup & Import

> [!NOTE]
> Last updated: `September 8, 2026`

**Base path:** `/api/admin`

All download endpoints require a valid session. The import endpoint requires `require_admin_mode`.

### Export tags as CSV

Downloads all tags and aliases as a CSV file in the same format accepted by the CSV importer.

```
GET /api/admin/backup/tags
```

**Response:** `text/csv` file download named `blombooru_tags-<timestamp>.csv`.

### Export all media files

Downloads a ZIP archive containing every original media file.

```
GET /api/admin/backup/media
```

**Response:** `application/zip` file download named `blombooru_media_backup-<timestamp>.zip`.

### Full backup

Downloads a ZIP archive that bundles all original media files, custom themes (`custom_themes/*.css`), a `tags.csv` export, and a `backup.json` file containing complete application and database state.

> [!WARNING]
> Full backups should **not** be shared publicly as they include saved credentials and API keys for external booru accounts (under `booru_config`).

> [!NOTE]
> API keys generated for this Blombooru instance are **not** included in backups and must be recreated if restoring on a separate instance.
> Host infrastructure secrets (`database` password, `redis` password, `shared_tags` password, host `secret_key`, and the admin user password hash) are strictly excluded from backup exports. All other application settings from `settings.json` are automatically exported and imported.

```
GET /api/admin/backup/full
```

**Response:** `application/zip` file download named `blombooru_full_backup-<timestamp>.zip`.

The `backup.json` contains:

```json
{
  "version": "<app_version>",
  "schema_version": "<schema_version>",
  "type": "full_backup",
  "exported_at": "2026-08-14T10:00:00+00:00",
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
      "source": "https://example.com/art.jpg",
      "description": "Artwork description",
      "uploaded_at": "2026-08-14T10:00:00+00:00",
      "is_shared": false,
      "share_uuid": null,
      "share_ai_metadata": false,
      "share_language": null,
      "transcoded_path": "media/transcoded/img.webp",
      "tags": ["fox", "landscape"],
      "archive_path": "media/img.jpg",
      "parent_hash": null
    }
  ],
  "albums": [
    {
      "id": 1,
      "name": "My Album",
      "created_at": "2026-08-14T10:00:00+00:00",
      "updated_at": "2026-08-14T10:00:00+00:00",
      "last_modified": "2026-08-14T10:00:00+00:00",
      "media": [
        {
          "hash": "abc123",
          "added_at": "2026-08-14T10:00:00+00:00"
        }
      ],
      "media_hashes": ["abc123"],
      "child_ids": []
    }
  ],
  "tag_implications": [
    {
      "target_tags": ["fox_ears"],
      "target_tag_patterns": ["*_ears"],
      "implied_tags": ["animal_ears"],
      "created_at": "2026-08-14T10:00:00+00:00"
    }
  ],
  "booru_config": [
    {
      "domain": "danbooru.donmai.us",
      "username": "user",
      "api_key": "key123",
      "created_at": "2026-08-14T10:00:00+00:00",
      "updated_at": "2026-08-14T10:00:00+00:00"
    }
  ],
  "custom_themes": [
    {
      "id": "custom_solarized_dark",
      "name": "Solarized Dark",
      "is_dark": true,
      "primary_color": "#268bd2",
      "background_color": "#002b36",
      "backup_theme_id": "default_dark",
      "created_at": "2026-08-14T10:00:00+00:00"
    }
  ],
  "settings": {
    "app_name": "Blombooru",
    "items_per_page": 64,
    "default_sort": "uploaded_at",
    "default_order": "desc",
    "popular_tags_mode": "current_page",
    "popular_tags_limit": 20,
    "sidebar_filter_mode": "rating",
    "sidebar_custom_buttons": [],
    "media_type_tags": {"image": [], "gif": [], "video": []},
    "wd_tagger": {
      "general_threshold": 0.35,
      "character_threshold": 0.85,
      "model_name": "wd-eva02-large-tagger-v3",
      "blacklisted_tags": []
    },
    "custom_background": {
      "enabled": false,
      "media_id": null,
      "media_hash": null
    },
    "keybindings": {},
    "theme": "default_dark",
    "language": "en",
    "external_share_url": null,
    "require_auth": false
  }
}
```

### Import a full backup

Requires `require_admin_mode`. Accepts the ZIP file produced by the full backup endpoint. Media files requiring transcoding are automatically transcoded upon import, and thumbnails are generated accordingly.

```
POST /api/admin/import/full
Content-Type: multipart/form-data

file=<zip-file>
```

**Response:**

```json
{
  "message": "Import completed successfully",
  "stats": {
    "tags": {
      "tags_created": 10,
      "tags_updated": 2,
      "aliases_created": 5
    },
    "media": {
      "imported": 50,
      "skipped": 0,
      "total": 50
    },
    "albums": {
      "albums_created": 3,
      "albums_existing": 0,
      "links_created": 50
    },
    "tag_implications": {
      "imported": 2,
      "skipped": 0
    },
    "booru_config": {
      "imported": 1
    },
    "custom_themes": {
      "imported": 1
    },
    "settings": {
      "imported": true
    }
  }
}
```
