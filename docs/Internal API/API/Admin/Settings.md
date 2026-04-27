## Admin: Settings

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

### Test Redis connection

Requires `require_admin_mode`.

```
POST /api/admin/test-redis
Content-Type: application/json

{ "host": "redis", "port": 6379, "db": 0, "password": null }
```

**Response:** `{ "success": true }` or `{ "success": false, "error": "..." }`

### Get available themes

```
GET /api/admin/themes
```

### Get current theme (public)

```
GET /api/admin/current-theme
```

### Get available languages

```
GET /api/admin/languages
```

### Get translations

```
GET /api/admin/translations?lang=en
```
