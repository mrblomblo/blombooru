## Tags

**Base path:** `/api/tags`

### List / filter tags

```
GET /api/tags
```

| Query param | Type | Description |
|---|---|---|
| `search` | string | Substring match on tag name |
| `names` | string | Comma-separated exact tag names |
| `category` | string | Filter by category |
| `limit` | int | Max results (default: 100) |

**Response:** `TagResponse[]`

```json
[
  { "id": 1, "name": "fox", "category": "general", "post_count": 42, "created_at": "..." }
]
```

### Get tag autocomplete suggestions

```
GET /api/tags/autocomplete?q=<prefix>
```

Returns up to 50 results including tag aliases, merged with shared tags if configured:

```json
[
  { "name": "fox", "category": "general", "count": 42 },
  { "name": "fox_(character)", "category": "character", "count": 5, "is_alias": true, "alias_name": "fox_char" }
]
```

### Get single tag

```
GET /api/tags/{name}
```

**Response:** `TagResponse`

### Get related tags (for a single tag)

```
GET /api/tags/{name}/related?limit=20
```

Returns tags that frequently appear alongside this one, ordered by co-occurrence count.

### Get related tags (for multiple tags)

```
GET /api/tags/related?tags=tag1,tag2
```

Returns up to 20 tags that frequently co-occur with the given set, excluding the input tags.

### Create tag

Requires `require_admin_mode`.

```
POST /api/tags
Content-Type: application/json

{ "name": "mytag", "category": "general" }
```

**Response:** `TagResponse`

### Update tag category

Requires `require_admin_mode`.

```
PATCH /api/tags/{id}?category=artist
```

### Delete tag

Requires `require_admin_mode`.

```
DELETE /api/tags/{id}
```
