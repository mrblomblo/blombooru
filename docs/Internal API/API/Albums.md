## Albums

**Base path:** `/api/albums`

### List albums

```
GET /api/albums
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `page` | int | 1 | |
| `limit` | int | settings | |
| `sort` | string | `created_at` | `created_at`, `name`, `last_modified` |
| `order` | string | `desc` | `asc` or `desc` |
| `rating` | string | | Rating filter |
| `root_only` | bool | false | Only return top-level albums (not children of any album) |

**Response:** `{ "items": AlbumListResponse[], "total", "page", "limit", "pages" }`

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
| `page` | int | 1 | |
| `limit` | int | settings | |
| `q` | string | | Tag search query applied to media |
| `rating` | string | | Rating filter |
| `sort` | string | `uploaded_at` | |
| `order` | string | `desc` | |

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
