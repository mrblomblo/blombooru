## Tag Implications

**Base path:** `/api/tag-implications`

All endpoints require `require_admin_mode`.

Tag implications automatically add a set of implied tags when any of the target tags are applied to media.

### List implications

```
GET /api/tag-implications
```

**Response:**

```json
[
  {
    "id": 1,
    "target_tags": [ { "id": 10, "name": "corgi" } ],
    "implied_tags": [ { "id": 5, "name": "dog" } ]
  }
]
```

### Create implication

```
POST /api/tag-implications
Content-Type: application/json

{
  "target_tags": ["corgi"],
  "implied_tags": ["dog", "canine"]
}
```

All tag names must already exist.

### Update implication

```
PUT /api/tag-implications/{id}
Content-Type: application/json

{ "target_tags": ["corgi"], "implied_tags": ["dog"] }
```

### Delete implication

```
DELETE /api/tag-implications/{id}
```
