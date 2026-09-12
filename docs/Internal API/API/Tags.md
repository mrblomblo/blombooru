## Tags

> [!NOTE]
> Last updated: `September 8, 2026`

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

Returns up to 50 prefix-matched results including tag aliases, merged with shared tags if configured:

```json
[
  { "name": "fox", "category": "general", "count": 42 },
  { "name": "fox_(character)", "category": "character", "count": 5, "is_alias": true, "alias_name": "fox_char" }
]
```

### Get suggested tags (TF-IDF similarity)

Returns suggested tags based on a category-weighted TF-IDF similarity index built across media posts. Unlike prefix autocomplete, this suggests contextually relevant co-occurring tags for an existing set of tags.

```
GET /api/tags/suggested
```

| Query param | Type | Description |
|---|---|---|
| `tags` | string | Comma-separated list of tag names |
| `limit` | int | Max results (1 to 50, default: 20) |
| `category` | string | Optional category filter (`general`, `artist`, `character`, `copyright`, `meta`) |

**Response (ready):**

```json
{
  "items": [
    {
      "id": 42,
      "name": "tail",
      "category": "general",
      "post_count": 180,
      "cosine_similarity": 0.8421
    }
  ],
  "status": "ready"
}
```

If the similarity index is rebuilding in the background, the endpoint waits up to 10 seconds. If still not ready, it returns:

```json
{
  "items": [],
  "status": "building"
}
```

### Batch validate tags

Resolves a list of tag names against the database, resolving aliases to their canonical target names and checking category metadata.

```
POST /api/tags/batch-validate
Content-Type: application/json

{
  "names": ["corgi", "fox_alias", "unknown_tag"]
}
```

**Response:**

```json
{
  "resolved": {
    "corgi": { "name": "corgi", "category": "general" },
    "fox_alias": { "name": "fox", "category": "general" },
    "unregistered_alias": { "name": "target_tag", "category": null },
    "unknown_tag": null
  }
}
```

- If the tag exists in the database, its canonical name and category are returned.
- If the tag is an alias pointing to a target that is not yet created in the database, `category` is `null`.
- If the tag does not exist and is not an alias, `null` is returned for that key.

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

### Get related tags for a search query

```
GET /api/tags/search-related?q=<query>&rating=<rating>&limit=20
```

| Query param | Type | Description |
|---|---|---|
| `q` | string | Full search query string (same syntax as `/api/search`) |
| `rating` | string | Optional rating filter |
| `limit` | int | Max results (1 to 100, default: 20) |

Returns the tags most commonly found on the results of the given query, ordered by frequency. Input tags already present in the query are excluded from the results.

**Response:**

```json
[
  { "name": "fox", "category": "general", "count": 42, "frequency": 15 }
]
```

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
