## Albums

> [!NOTE]
> Last updated: `October 10, 2026`

**Base path:** `/api/albums`

### List albums

```
GET /api/albums
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `page` | int | 1 | Page number |
| `limit` | int | settings | Items per page |
| `sort` | string | `created_at` | Sort field: `created_at`, `name`, `last_modified`, or `manual` (when `root_only=true`) |
| `order` | string | `desc` | `asc` or `desc` |
| `fallback_sort` | string | `created_at` | Fallback sort field when `sort=manual` |
| `fallback_order` | string | `desc` | Fallback sort order (`asc` or `desc`) when `sort=manual` |
| `seed` | string | | Seed string for randomized sorting |
| `rating` | string | | Rating filter |
| `custom_filter` | string[] | | Custom filter tag expressions |
| `q` | string | | Search query |
| `root_only` | bool | false | Only return top-level albums (not children of any album) |

**Response:** `{ "items": AlbumListResponse[], "total": int, "page": int, "limit": int, "pages": int }`

### Reorder root albums

Requires `require_admin_mode`. Sets explicit manual sort positions for root albums.

```
PUT /api/albums/reorder
Content-Type: application/json

{ "album_ids": [3, 1, 2] }
```

**Response:** `{ "message": "Root album order updated" }`

### Clear root albums manual order

Requires `require_admin_mode`. Resets manual sort positions for all root albums.

```
DELETE /api/albums/reorder
```

**Response:** `{ "message": "Root album manual order cleared" }`

### Get album tree

```
GET /api/albums/tree
```

Returns all albums as a flat list ordered by name. Use `parent_id` and `depth` to reconstruct the hierarchy.

**Response:** `AlbumHierarchyResponse`

```json
{
  "items": [
    {
      "id": 1,
      "name": "Artworks",
      "parent_id": null,
      "depth": 0,
      "media_count": 25,
      "direct_media_count": 10,
      "children_count": 1,
      "rating": "safe"
    },
    {
      "id": 2,
      "name": "Sketches",
      "parent_id": 1,
      "depth": 1,
      "media_count": 15,
      "direct_media_count": 15,
      "children_count": 0,
      "rating": "safe"
    }
  ]
}
```

### Get album statistics

```
GET /api/albums/stats
```

**Response:** `AlbumStatsResponse`

```json
{
  "total_albums": 12,
  "root_albums": 4,
  "total_media_in_albums": 350
}
```

### Recalculate all album metrics

Requires `require_admin_mode`. Re-indexes cached media counts, direct media counts, and rating aggregations across all albums, then purges the album cache.

```
POST /api/albums/recalculate
```

**Response:** `{ "message": "All album metrics successfully recalculated and cache invalidated" }`

### Prune empty leaf albums

Requires `require_admin_mode`. Deletes all empty leaf albums that contain no media and have no child albums.

```
POST /api/albums/prune
```

**Response:** `{ "message": "Albums have been pruned successfully", "count": 2 }`

### Autocomplete albums

```
GET /api/albums/autocomplete?q=sketch&limit=50
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `q` | string | | Search term (min length: 1) |
| `limit` | int | 50 | Maximum number of results (1-100) |

**Response:**

```json
[
  {
    "id": 2,
    "name": "Sketches",
    "parent_path": "Artworks",
    "media_count": 15,
    "rating": "safe"
  }
]
```

### Get album

```
GET /api/albums/{id}
```

**Response:** `AlbumResponse`

```json
{
  "id": 1,
  "name": "My Album",
  "created_at": "...",
  "updated_at": "...",
  "last_modified": "...",
  "media_count": 5,
  "children_count": 2,
  "rating": "safe",
  "parent_ids": []
}
```

### Create album

Requires `require_admin_mode`.

```
POST /api/albums
Content-Type: application/json

{ "name": "My Album", "parent_album_id": null }
```

### Update album

Requires `require_admin_mode`.

```
PUT /api/albums/{id}
Content-Type: application/json

{ "name": "New Name", "parent_album_id": 5 }
```

### Delete album

Requires `require_admin_mode`.

```
DELETE /api/albums/{id}?cascade=false
```

Without `cascade=true`, child albums are orphaned (parent relationship removed). With `cascade=true`, child albums are deleted recursively. Media items are never deleted by album deletion.

### Album contents

```
GET /api/albums/{id}/contents
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `page` | int | 1 | Page number |
| `limit` | int | settings | Items per page |
| `q` | string | | Tag search query applied to media |
| `rating` | string | | Rating filter |
| `custom_filter` | string[] | | Custom filter tag expressions |
| `sort` | string | `uploaded_at` | Sort field: `uploaded_at`, `filename`, `file_size`, or `manual` |
| `order` | string | `desc` | `asc` or `desc` |
| `fallback_sort` | string | `uploaded_at` | Fallback sort field when `sort=manual` |
| `fallback_order` | string | `desc` | Fallback sort order when `sort=manual` |
| `seed` | string | | Seed string for randomized sorting |

**Response:**

```json
{
  "media": [ /* MediaResponse[] */ ],
  "albums": [ /* AlbumListResponse[] - direct child albums */ ],
  "total_media": 10,
  "page": 1,
  "limit": 20,
  "pages": 1
}
```

### Add media to album (bulk)

Requires `require_admin_mode`.

```
POST /api/albums/{id}/media
Content-Type: application/json

{ "media_ids": [1, 2, 3] }
```

### Remove media from album (bulk)

Requires `require_admin_mode`.

```
DELETE /api/albums/{id}/media
Content-Type: application/json

{ "media_ids": [1, 2] }
```

### Reorder media in album

Requires `require_admin_mode`. Sets explicit manual sort positions for media within an album.

```
PUT /api/albums/{id}/media/reorder
Content-Type: application/json

{ "media_ids": [3, 1, 2] }
```

**Response:** `{ "message": "Album media order updated" }`

### Clear media manual order in album

Requires `require_admin_mode`. Resets manual media sort positions for the specified album.

```
DELETE /api/albums/{id}/media/reorder
```

**Response:** `{ "message": "Manual media order cleared" }`

### Reorder sub-albums in album

Requires `require_admin_mode`. Sets explicit manual sort positions for child albums under the specified parent album.

```
PUT /api/albums/{id}/sub-albums/reorder
Content-Type: application/json

{ "album_ids": [5, 4] }
```

**Response:** `{ "message": "Sub-album order updated" }`

### Clear sub-albums manual order in album

Requires `require_admin_mode`. Resets manual sub-album sort positions under the specified parent album.

```
DELETE /api/albums/{id}/sub-albums/reorder
```

**Response:** `{ "message": "Manual sub-album order cleared" }`

### Popular tags in album

```
GET /api/albums/{id}/tags?limit=20
```

Returns `{ "tags": [ { "name", "category", "count" } ] }`.

### Child albums

```
GET /api/albums/{id}/children
```

Returns `AlbumListResponse[]`.

### Parent album chain (breadcrumb)

```
GET /api/albums/{id}/parents
```

Returns `{ "parents": [ { "id", "name" } ] }` ordered from root to immediate parent.
