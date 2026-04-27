## Admin: Tags

**Base path:** `/api/admin`

### Tag statistics

Requires a valid session.

```
GET /api/admin/tag-stats
```

**Response:** `{ "total_tags": 5000, "total_aliases": 200 }`

### Search tags (admin)

Requires a valid session.

```
GET /api/admin/search-tags?q=fox
```

Returns `{ "tags": TagResponse[] }` (up to 50 results).

### Import tags from CSV

Requires `require_admin_mode`. Accepts a CSV file in the Danbooru tag export format: `name,category_id,post_count,aliases`.

```
POST /api/admin/import-tags-csv
Content-Type: multipart/form-data

file=<csv-file>
```

Category IDs: `0` = general, `1` = artist, `3` = copyright, `4` = character, `5` = meta.

**Response:** `{ "tags_created", "tags_updated", "aliases_created", "rows_processed", "errors": [...] }`

### Bulk create tags

Requires `require_admin_mode`.

```
POST /api/admin/bulk-create-tags
Content-Type: application/json

{
  "tags": [
    { "name": "fox", "category": "general" },
    { "name": "bob", "category": "artist" }
  ]
}
```

**Response:** `{ "created", "skipped", "errors" }`

### Delete a tag (admin)

Requires `require_admin_mode`.

```
DELETE /api/admin/tags/{id}
```

Also deletes from the shared tag database if shared tags are enabled.

### Delete all tags

Requires `require_admin_mode`. Removes all tags and aliases from the database. **Irreversible.**

```
DELETE /api/admin/clear-tags
```

### Check alias existence

Requires `require_admin_mode`.

```
GET /api/admin/check-alias?name=fox_char
```

**Response:** `{ "exists": true }`
