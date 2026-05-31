## Admin: Shared Tags

> [!NOTE]
> Last updated: `May 31, 2026`

**Base path:** `/api/admin`

All endpoints require `require_admin_mode`.

### Test shared tag database connection

```
POST /api/admin/test-shared-tag-db
Content-Type: application/json

{
  "host": "shared-tag-db",
  "port": 5432,
  "name": "shared_tags",
  "user": "postgres",
  "password": "..."
}
```

**Response:** `{ "success": true }` or `{ "success": false, "message": "..." }`

### Get shared tag database status

```
GET /api/admin/shared-tags/status
```

**Response:**

```json
{
  "enabled": true,
  "connected": true,
  "error": null,
  "config": {
    "host": "shared-tag-db",
    "port": 5432,
    "name": "shared_tags",
    "user": "postgres"
  },
  "local_tags": 5000,
  "local_aliases": 200,
  "shared_tags": 4800,
  "shared_aliases": 190
}
```

`shared_tags` and `shared_aliases` are only present when the shared database is reachable.

### Sync with shared tag database

Triggers a full bidirectional sync: local tags are pushed to the shared database and new shared tags are pulled into the local database.

```
POST /api/admin/shared-tags/sync
```

Returns `400` if shared tags are not enabled, or `503` if the database is not reachable.

**Response:**

```json
{
  "success": true,
  "tags_imported": 12,
  "tags_exported": 3,
  "aliases_imported": 5,
  "aliases_exported": 1,
  "conflicts_resolved": 0,
  "errors": []
}
```

### Reconnect to shared tag database

Attempts to re-establish the connection after a failure.

```
POST /api/admin/shared-tags/reconnect
```

Returns `400` if shared tags are not enabled.

**Response:** `{ "success": true, "message": "Reconnected successfully" }` or `{ "success": false, "message": "<error>" }`
