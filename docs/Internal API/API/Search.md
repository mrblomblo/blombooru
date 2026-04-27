## Search

**Base path:** `/api/search`

### Search media by tags and metadata

```
GET /api/search?q=<query>
```

| Query param | Type | Description |
|---|---|---|
| `q` | string | Tag-based query string (supports negation with `-tag`, metatags like `rating:safe`, etc.) |
| `rating` | string | Rating filter applied on top of the query |
| `page` | int | Page number |
| `limit` | int | Items per page |

**Response:**

```json
{
  "items": [ /* MediaResponse[] */ ],
  "total": 42,
  "page": 1,
  "pages": 5,
  "query": "fox -wolf"
}
```

### Get a random matching media ID

```
GET /api/search/random?q=<query>&rating=<rating>
```

**Response:** `{ "id": 123 }` or `{ "id": null }` if nothing matches.
