## Admin: Custom Themes

> [!NOTE]
> Last updated: `May 30, 2026`

**Base path:** `/api/admin`

All endpoints require an active admin session (`require_admin_mode`).

---

### List built-in themes (for backup theme selector)

Returns only non-custom (built-in) themes for use in the backup theme dropdown.

```
GET /api/admin/builtin-themes
```

**Response:** `{ "themes": ThemeMetadata[] }` (sorted by name, `is_custom` is always `false`)

---

### List custom themes

```
GET /api/admin/custom-themes
```

**Response:**

```json
{
  "themes": [
    {
      "id": "custom_my_theme",
      "name": "My Theme",
      "is_dark": true,
      "primary_color": "#ff6600",
      "background_color": "#1a1a1a",
      "created_at": "2026-05-30T12:00:00+00:00",
      "is_active": false
    }
  ]
}
```

---

### Create a custom theme

Creates a new theme from inline CSS text. The CSS is sanitized before being stored.

```
POST /api/admin/custom-themes
Content-Type: application/json

{
  "name": "My Theme",
  "is_dark": true,
  "backup_theme_id": "default_dark",
  "css": ":root { --primary-color: #ff6600; }"
}
```

**Response:** `{ "theme": ThemeMetadata }`

**Errors:**
- `400` -- name missing, CSS empty, or CSS failed sanitization
- `413` -- CSS exceeds the 50 KB limit

---

### Import a custom theme

Accepts a `.blombooru-theme` ZIP bundle or a raw `.css` file.

The `.blombooru-theme` bundle format is a ZIP archive containing:
- `theme.css` -- the CSS source
- `theme.json` -- metadata: `{ name, is_dark, exported_at, app_version }`

Form fields `name` and `is_dark` always take precedence over bundle metadata.

```
POST /api/admin/custom-themes/import
Content-Type: multipart/form-data

file=<.blombooru-theme or .css file>
name=<optional override>
is_dark=<"true" or "false">
```

**Response:** `{ "theme": ThemeMetadata }`

**Errors:**
- `400` -- invalid file format or CSS sanitization failure
- `413` -- file exceeds the 50 KB limit

---

### Update a custom theme

Updates name, `is_dark`, and/or CSS content. All fields are optional.

```
PUT /api/admin/custom-themes/{theme_id}
Content-Type: application/json

{
  "name": "New Name",
  "is_dark": false,
  "backup_theme_id": "dracula",
  "css": ".sidebar { background: red; }"
}
```

**Response:** `{ "theme": ThemeMetadata }`

**Errors:**
- `404` -- theme not found
- `400` -- validation failure

---

### Delete a custom theme

```
DELETE /api/admin/custom-themes/{theme_id}
```

**Errors:**
- `404` -- theme not found
- `409` -- theme is currently active (switch themes first)

**Response:** `{ "message": "Theme deleted" }`

---

### Export a custom theme

Downloads the theme as a `.blombooru-theme` ZIP bundle.

```
GET /api/admin/custom-themes/{theme_id}/export
```

**Response:** `application/zip` file download named `<theme_name>.blombooru-theme`

**Errors:**
- `404` -- theme not found or CSS file missing
