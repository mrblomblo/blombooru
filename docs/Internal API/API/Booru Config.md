## Booru Configuration

**Base path:** `/api/booru-config`

Manages credentials for external booru domains used by the importer.

All endpoints require `require_admin_mode`.

### List configured boorus

```
GET /api/booru-config
```

**Response:** Array of `{ "domain", "username", "created_at", "updated_at", "has_api_key" }`. API keys are never returned in plaintext.

### Create or update booru config

```
POST /api/booru-config
Content-Type: application/json

{
  "domain": "danbooru.donmai.us",
  "username": "myuser",
  "api_key": "abc123"
}
```

If a config for the domain already exists it is updated; otherwise a new one is created. The scheme prefix and trailing slash are stripped automatically.

### Delete booru config

```
DELETE /api/booru-config/{domain}
```
