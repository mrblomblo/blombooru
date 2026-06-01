## Instance Info

> [!NOTE]
> Last updated: `June 1, 2026`

**Base path:** `/api`

### Get instance info

No auth required. Returns harmless public metadata consumed by the frontend on first load.

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
  }
}
```

> [!NOTE]
> `app_version` can also contain letters, such as `1.40.0-rc1`
