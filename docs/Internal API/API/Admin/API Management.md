## Admin: API Keys

**Base path:** `/api/admin`

All endpoints require `require_admin_mode`.

### List API keys

```
GET /api/admin/api-keys
```

**Response:** `ApiKeyListResponse[]`

```json
[
  {
    "id": 1,
    "key_prefix": "blom_abc123",
    "name": "My Script",
    "created_at": "...",
    "last_used_at": "...",
    "is_active": true
  }
]
```

### Create API key

```
POST /api/admin/api-keys
Content-Type: application/json

{ "name": "My Script" }
```

**Response:** `ApiKeyResponse` with the full `key` value (only returned once; store it securely):

```json
{
  "id": 1,
  "key": "blom_<full-key>",
  "key_prefix": "blom_abc123",
  "name": "My Script",
  "created_at": "..."
}
```

### Revoke API key

```
DELETE /api/admin/api-keys/{id}
```
