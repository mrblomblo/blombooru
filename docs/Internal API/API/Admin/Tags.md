## Admin: Tags

> [!NOTE]
> Last updated: `November 20, 2026`

**Base path:** `/api/admin`

### Tag statistics

Requires a valid session.

```
GET /api/admin/tag-stats
```

**Response:** `{ "total_tags": 5000, "total_aliases": 200, "total_implications": 50 }`

### Search tags (admin)

Requires a valid session.

```
GET /api/admin/search-tags?q=fox
```

Returns `{ "tags": TagResponse[] }` (up to 50 results).

### Get tag details (admin)

Requires `require_admin_mode`. Returns tag details including post count and aliases.

```
GET /api/admin/tags/{id}
```

**Response:**
```json
{
  "id": 123,
  "name": "fox",
  "category": "general",
  "post_count": 42,
  "aliases": ["kitsune", "renard"]
}
```

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

### Rename or update a tag (admin)

Requires `require_admin_mode`. Renames the tag, changes its category, and/or updates its aliases.

```
PUT /api/admin/tags/{id}
Content-Type: application/json

{
  "name": "new_name",
  "category": "artist",
  "aliases": ["kitsune", "renard"]
}
```

The `aliases` array is optional. If provided, it replaces the tag's current aliases. Returns `409` if the new name or any specified alias conflicts with an existing tag or alias.

**Response:** `{ "old_name": "fox", "tag_name": "new_name", "category": "artist", "aliases": ["kitsune", "renard"] }`

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

### Simulate applying tag aliases to all media

Requires `require_admin_mode`. **Read-only.** Scans all media to identify tags that match defined aliases and returns the affected media along with proposed tag additions and removals. Does not modify any data.

```
POST /api/admin/simulate-apply-aliases
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `background` | bool | `false` | When `true`, starts the simulation in the background (`apply_aliases`) instead of waiting for completion |

**Response (`background=false`):**
```json
{
  "affected_media": [
    {
      "media_id": 1,
      "added_tags": ["fox"],
      "removed_tags": ["kitsune"]
    }
  ]
}
```

**Response (`background=true`):** `{ "status": "started" | "already_running", "job": { ... } }`

### Simulate applying tag ratings to all media

Requires `require_admin_mode`. **Read-only.** Scans non-explicit media to identify items whose rating should be escalated based on configured tag ratings. Does not modify any data.

```
POST /api/admin/simulate-apply-tag-ratings
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `background` | bool | `false` | When `true`, starts the simulation in the background (`apply_tag_ratings`) instead of waiting for completion |

**Response (`background=false`):**
```json
{
  "affected_media": [
    {
      "media_id": 1,
      "current_rating": "safe",
      "new_rating": "questionable"
    }
  ]
}
```

**Response (`background=true`):** `{ "status": "started" | "already_running", "job": { ... } }`

### Cleanup aliased tags

Requires `require_admin_mode`. Deletes any `Tag` database records whose names match defined alias names in `TagAlias`, ensuring a tag cannot exist as both a tag and an alias simultaneously.

```
POST /api/admin/cleanup-aliased-tags
```

**Response:** `{ "deleted_count": 3 }`
