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
  "theme": { /* ThemeMetadata */ },
  "language": {
    "id": "en",
    "name": "English",
    "native_name": "English"
  }
}
```

> [!NOTE]
> `app_version` can also contain letters, such as `1.40.0-rc1`
