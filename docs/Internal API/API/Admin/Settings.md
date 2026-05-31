## Admin: Settings

> [!NOTE]
> Last updated: `May 31, 2026`

**Base path:** `/api/admin`

### Get settings

Requires a valid session (JWT only; does not require `admin_mode` cookie).

```
GET /api/admin/settings
```

Returns the current settings object with sensitive fields (`secret_key`, database/redis passwords) redacted.

### Update settings

Requires `require_admin_mode`.

```
PATCH /api/admin/settings
Content-Type: application/json

{
  "app_name": "My Booru",
  "items_per_page": 50,
  "default_sort": "uploaded_at",
  "default_order": "desc",
  "theme": "default_dark",
  "language": "en",
  "external_share_url": null,
  "require_auth": false,
  "sidebar_filter_mode": "standard",
  "sidebar_custom_buttons": [],
  "redis": { "enabled": true, "host": "redis", "port": 6379, "db": 0, "password": null },
  "shared_tags": { "enabled": false, "host": "shared-tag-db", "port": 5432, "name": "shared_tags", "user": "postgres", "password": null }
}
```

All fields are optional; only supplied fields are updated.

> [!NOTE]
> Password fields (`redis.password`, `shared_tags.password`) are returned as `"***"` by `GET /api/admin/settings`. Sending `"***"` back in a PATCH leaves the stored password unchanged. Send `null` to clear a password, or send the new plaintext value to change it.

### Test Redis connection

Requires `require_admin_mode`.

```
POST /api/admin/test-redis
Content-Type: application/json

{ "host": "redis", "port": 6379, "db": 0, "password": null }
```

**Response:** `{ "success": true }` or `{ "success": false, "error": "..." }`

### Get available themes

No auth required.

```
GET /api/admin/themes
```

**Response:** `{ "themes": ThemeMetadata[], "current_theme": "default_dark" }`

### Get instance info

No auth required. Returns harmless public metadata consumed by the frontend on first load.

```
GET /api/admin/instance-info
```

**Response:**

```json
{
  "app_name": "Blombooru",
  "app_version": "1.2.0",
  "auth_required": false,
  "theme": { /* ThemeMetadata */ },
  "language": {
    "id": "en",
    "name": "English",
    "native_name": "English"
  }
}
```

### Get available languages

No auth required.

```
GET /api/admin/languages
```

**Response:** `{ "languages": LanguageMetadata[], "current_language": "en" }`

### Get translations

No auth required.

```
GET /api/admin/translations?lang=en
```

Returns the full translation string map for the requested language (or the currently configured language if `lang` is omitted).
