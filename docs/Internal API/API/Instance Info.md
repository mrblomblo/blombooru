## Instance Info

> [!NOTE]
> Last updated: `September 8, 2026`

**Base path:** `/api`

### Get instance info

No auth required. Returns harmless public metadata consumed by the frontend on first load to configure theme, localization, keybindings, and format support.

```
GET /api/instance-info
```

**Response:**

```json
{
  "app_name": "Blombooru",
  "app_version": "1.40.0",
  "auth_required": false,
  "theme": {
    "id": "ctp_mocha",
    "name": "Catppuccin Mocha",
    "css_path": "/static/css/themes/ctp_mocha.css",
    "is_dark": true,
    "primary_color": "#fab387",
    "background_color": "#11111b",
    "is_custom": false,
    "backup_theme": {
      "id": "default_dark",
      "name": "Default Dark",
      "css_path": "/static/css/themes/default_dark.css",
      "is_dark": true,
      "primary_color": "#3b82f6",
      "background_color": "#0f172a",
      "is_custom": false
    }
  },
  "language": {
    "id": "en",
    "name": "English",
    "native_name": "English"
  },
  "keybindings": {
    "next_media": { "code": "KeyD", "key": "d" },
    "previous_media": { "code": "KeyA", "key": "a" },
    "close_modal": { "code": "Escape", "key": "Escape" }
  },
  "supported_formats": {
    ".jpg": {
      "extension": ".jpg",
      "mime_type": "image/jpeg",
      "category": "image",
      "transcode_target": null,
      "requires_transcode": false,
      "aliases": [".jpeg"]
    },
    ".heic": {
      "extension": ".heic",
      "mime_type": "image/heic",
      "category": "image",
      "transcode_target": ".webp",
      "requires_transcode": true,
      "aliases": [".heif"]
    },
    ".mp4": {
      "extension": ".mp4",
      "mime_type": "video/mp4",
      "category": "video",
      "transcode_target": null,
      "requires_transcode": false,
      "aliases": []
    },
    ".mkv": {
      "extension": ".mkv",
      "mime_type": "video/x-matroska",
      "category": "video",
      "transcode_target": ".mp4",
      "requires_transcode": true,
      "aliases": []
    },
    ".zip": {
      "extension": ".zip",
      "mime_type": "application/zip",
      "category": "archive",
      "transcode_target": null,
      "requires_transcode": false,
      "aliases": []
    }
  }
}
```

### Supported Format Entry Fields

| Field | Type | Description |
|---|---|---|
| `extension` | string | Normalized primary file extension including the leading dot |
| `mime_type` | string | Canonical MIME type |
| `category` | string | Format category: `image`, `video`, `archive`, `document`, `data`, or `theme` |
| `transcode_target` | string \| null | Target extension if the file requires transcoding before playback (e.g. `.webp` or `.mp4`), otherwise `null` |
| `requires_transcode` | boolean | `true` if server-side transcoding will be performed upon ingestion |
| `aliases` | string[] | List of alternative extensions that map to this format (e.g. `[".jpeg"]` or `[".heif"]`) |

> [!NOTE]
> `app_version` can also contain letters, such as `1.40.0-rc1`
