## Tag Implications

> [!NOTE]
> Last updated: `November 20, 2026`

**Base path:** `/api/tag-implications`

All endpoints require `require_admin_mode`.

Tag implications automatically add a set of implied tags when target tags or target wildcard patterns are matched on media posts.

### List implications

Requires `require_admin_mode`. Returns existing implication rules, with support for pagination and text filtering.

```
GET /api/tag-implications?limit=50&offset=0&search=dog
```

| Query param | Type | Description |
|---|---|---|
| `limit` | int | Max results (1 to 1000, optional) |
| `offset` | int | Offset for pagination (default: 0) |
| `search` | string | Substring match against target tags, implied tags, and patterns |

When paginated, the total number of matching rules is returned in the `X-Total-Count` response header.

**Response:**

```json
[
  {
    "id": 1,
    "target_tags": [ { "id": 10, "name": "corgi" } ],
    "target_tag_patterns": ["*_corgi"],
    "implied_tags": [ { "id": 5, "name": "dog" } ],
    "created_at": "2026-08-14T10:00:00+00:00"
  }
]
```

Orphaned implication records (where cascading tag deletions removed all target or implied tags) are automatically cleaned up when this endpoint is called.

### Create implication

Requires `require_admin_mode`.

```
POST /api/tag-implications
Content-Type: application/json

{
  "target_tags": ["corgi"],
  "target_tag_patterns": ["*_corgi"],
  "implied_tags": ["dog", "canine"]
}
```

- At least one entry in either `target_tags` or `target_tag_patterns` is required.
- `implied_tags` must contain at least one tag.
- All tag names in `target_tags` and `implied_tags` must already exist in the database (returns `400` if any are missing).
- Returns `409` (`{"detail": "Implication already exist"}`) if an identical implication rule already exists.

**Response:** `TagImplicationResponse` (status code `201`)

### Update implication

Requires `require_admin_mode`.

```
PUT /api/tag-implications/{id}
Content-Type: application/json

{
  "target_tags": ["corgi"],
  "target_tag_patterns": ["*_corgi"],
  "implied_tags": ["dog"]
}
```

**Response:** `TagImplicationResponse`

### Delete implication

Requires `require_admin_mode`.

```
DELETE /api/tag-implications/{id}
```

**Response:** `{ "status": "success" }`

### Expand tag implications (preview)

Requires `require_admin_mode`. Computes the full transitive closure of all implied tags for a given list of tags based on active implication rules and patterns.

```
POST /api/tag-implications/expand
Content-Type: application/json

{
  "tags": ["corgi", "forest"],
  "new_tags": ["corgi"]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `tags` | string[] | Yes | All tags currently present on the item or input field |
| `new_tags` | string[] | No | Optional subset of `tags` to seed expansion from. When provided, only implications triggered by `new_tags` (or multi-target rules completed by `new_tags` alongside other tags in `tags`) are expanded. |

**Response:**

```json
{
  "implied_tags": ["canine", "dog"],
  "implied_by": {
    "dog": [["corgi"]],
    "canine": [["dog"]]
  }
}
```

Only newly implied tags that are not already present in the input `tags` list are returned in `implied_tags` (sorted alphabetically) and `implied_by`.

### Simulate applying all implications

Requires `require_admin_mode`. Performs an optimized in-memory simulation evaluating all implication rules against every media post in the database. Does not write changes to the database.

```
POST /api/tag-implications/simulate-apply-all
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `background` | bool | `false` | When `true`, starts the simulation in the background (`apply_implications`) instead of waiting for completion |

**Response (`background=false`):**

```json
{
  "affected_media": [
    {
      "media_id": 12,
      "added_tags": ["canine", "dog"],
      "implied_by": {
        "dog": [["corgi"]],
        "canine": [["dog"]]
      }
    }
  ]
}
```

**Response (`background=true`):** `{ "status": "started" | "already_running", "job": { ... } }`

### Backfill implied tags metadata

Requires `require_admin_mode`. Evaluates all active implication rules against existing media posts and retroactively marks tags already present on a post as `implied: true` (and populates `implied_by` with the matching trigger tag IDs) when their rule conditions are met on that post. Does not add new tags to posts.

```
POST /api/tag-implications/backfill-implied-tags
```

| Query param | Type | Default | Description |
|---|---|---|---|
| `background` | bool | `false` | When `true`, starts the backfill in the background (`backfill_implied_tags`) instead of waiting for completion |

**Response (`background=false`):**

```json
{
  "status": "success",
  "updated_media_count": 5,
  "updated_tags_count": 12
}
```

**Response (`background=true`):** `{ "status": "started" | "already_running", "job": { ... } }`
