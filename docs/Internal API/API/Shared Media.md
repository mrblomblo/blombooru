## Shared Media

> [!NOTE]
> Last updated: `May 31, 2026`

**Base path:** `/api/shared`

All endpoints are **public** (no authentication required). They are rate-limited per IP to prevent abuse.

These endpoints serve the read-only shared media view. A share link is generated via [Media share management](/docs/Internal%20API/API/Media.md).

### Get shared media info

```
GET /api/shared/{share_uuid}
```

**Response:**

```json
{
  "type": "media",
  "data": { /* SharedMediaResponse */ }
}
```

Returns `404` if the UUID does not match an active share link.

### Serve shared media file

```
GET /api/shared/{share_uuid}/file
```

Streams the original media file. If `share_ai_metadata` is `false` on the share, EXIF/generation metadata is stripped on the fly before serving.

### Serve shared thumbnail

```
GET /api/shared/{share_uuid}/thumbnail
```

Streams the JPEG thumbnail.

### Get shared media metadata

```
GET /api/shared/{share_uuid}/metadata
```

Returns extracted EXIF / AI generation metadata for the file. Returns `403` if the share was created with `share_ai_metadata: false`.

### Get shared file processing status

```
GET /api/shared/{share_uuid}/status
```

Used by the frontend to poll whether the metadata-stripped file cache is ready before serving the file.

**Response:** `{ "status": "ready" | "processing" | "not_stripped" | "error" }`

- `not_stripped` -- AI metadata sharing is enabled, so the original file is served directly without any processing.
- `processing` -- the stripped cache is being generated; poll again shortly.
- `ready` -- the stripped file cache is ready to serve.
