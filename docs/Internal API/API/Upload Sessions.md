## Upload Sessions

> [!NOTE]
> Last updated: `September 8, 2026`

**Base path:** `/api/uploads`

Upload sessions provide a staged, confirmation-first workflow for batch uploading media. Files are uploaded and inspected in a temporary session directory (`media/cache/upload-sessions/{session_id}`) where tags, categories, descriptions, and album paths can be reviewed, edited in bulk, and reconciled before committing into the permanent library.

Stale sessions older than 1 hour are automatically purged by a background cleanup task every 15 minutes.

Write operations and session management require `require_admin_mode`. Staged preview file and thumbnail streams are accessible during the active session.

---

### Create upload session

Requires `require_admin_mode`. Initializes a new staging session directory.

```
POST /api/uploads/sessions
```

**Response:**

```json
{
  "session_id": "4b684898-0c62-43ce-b391-fc539dfd4a79"
}
```

---

### Get upload session state

Requires `require_admin_mode`. Returns the session metadata and all staged items.

```
GET /api/uploads/sessions/{session_id}
```

**Response:**

```json
{
  "session_id": "4b684898-0c62-43ce-b391-fc539dfd4a79",
  "created_at": 1725810000.12,
  "updated_at": 1725810050.45,
  "items": [ /* UploadSessionItem[] */ ]
}
```

---

### Cancel and delete upload session

Requires `require_admin_mode`. Immediately purges the session directory and all staged raw files and thumbnails.

```
DELETE /api/uploads/sessions/{session_id}
```

**Response:**

```json
{
  "status": "deleted",
  "session_id": "4b684898-0c62-43ce-b391-fc539dfd4a79"
}
```

---

### Upload file to session

Requires `require_admin_mode`. Stages a single media file in the session, checks for duplicate content hashes against the database and the current session, analyzes media properties, generates a preview thumbnail, and dry-run validates candidate tags.

```
POST /api/uploads/sessions/{session_id}/files
Content-Type: multipart/form-data
```

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file | Yes | File binary data |
| `relative_path` | string | No | Relative path from client (preserves folder structure from directory drops or archives) |
| `base_rating` | string | No | Initial rating: `safe` (default), `questionable`, or `explicit` |
| `base_source` | string | No | Initial source URL |
| `base_tags` | string | No | Space-separated tag names |
| `base_album_ids` | string | No | Comma-separated existing album IDs |
| `category_hints` | string | No | JSON object mapping tag names to categories, e.g. `{"fox": "character"}` |
| `user_assigned_tags` | string | No | JSON array of tag names explicitly chosen by the user |
| `base_description` | string | No | Initial post description |

**Response:** `UploadSessionItem`

```json
{
  "item_id": "d4a79fc539df",
  "filename": "artwork.png",
  "staged_filename": "d4a79fc539df_artwork.png",
  "relative_path": "Drawings/artwork.png",
  "file_size": 1542030,
  "width": 1920,
  "height": 1080,
  "duration": null,
  "file_type": "image",
  "mime_type": "image/png",
  "hash": "8f481c4e7...3a",
  "rating": "safe",
  "source": "",
  "description": "",
  "tags": [
    {
      "name": "fox",
      "category": "general",
      "is_new": false,
      "user_assigned": false
    }
  ],
  "album_ids": [],
  "suggested_album_path": null
}
```

Returns `409` if the file hash matches an existing media post or another file staged in the same session.

---

### Serve staged thumbnail preview

Streams the preview JPEG thumbnail generated during staging.

```
GET /api/uploads/sessions/{session_id}/items/{item_id}/thumbnail
```

---

### Serve staged file preview

Streams the raw staged media file.

```
GET /api/uploads/sessions/{session_id}/items/{item_id}/file
```

---

### Re-analyze staged item

Requires `require_admin_mode`. Re-runs file dimension probing, regenerates preview thumbnails, and refreshes tag proposals against the database.

```
POST /api/uploads/sessions/{session_id}/items/{item_id}/analyze
```

| Query param | Type | Description |
|---|---|---|
| `category_hints` | string | Optional JSON string mapping tag names to categories |

**Response:** Updated `UploadSessionItem`.

---

### Update staged item

Requires `require_admin_mode`. Updates rating, tags, source, description, or album assignments for a single staged item.

```
PATCH /api/uploads/sessions/{session_id}/items/{item_id}
Content-Type: application/json

{
  "rating": "safe",
  "tags": [
    {
      "name": "forest",
      "category": "general",
      "is_new": true,
      "user_assigned": true
    }
  ],
  "source": "https://example.com/artist/post",
  "description": "Artwork description",
  "album_ids": [1],
  "suggested_album_path": "Drawings/2026"
}
```

**Response:** Updated `UploadSessionItem`.

---

### Bulk update staged items

Requires `require_admin_mode`. Applies batch edits to multiple staged items at once.

```
POST /api/uploads/sessions/{session_id}/items/bulk-update
Content-Type: application/json

{
  "item_ids": ["d4a79fc539df", "b91fc539df12"],
  "rating": "questionable",
  "source": "https://example.com/source",
  "description": "Batch description",
  "album_ids": [2],
  "add_album_ids": [3],
  "remove_album_ids": [1],
  "suggested_album_path": "Series/Vol1",
  "add_tags": ["new_tag"],
  "remove_tag_names": ["old_tag"]
}
```

**Response:**

```json
{
  "updated_count": 2,
  "items": [ /* UploadSessionItem[] */ ]
}
```

---

### Delete staged item

Requires `require_admin_mode`. Removes a single item from the session and deletes its staged raw file and thumbnail. If the session becomes empty, the session directory is deleted.

```
DELETE /api/uploads/sessions/{session_id}/items/{item_id}
```

**Response:**

```json
{
  "status": "deleted",
  "item_id": "d4a79fc539df",
  "session_empty": false
}
```

---

### Get pending entities (tags and albums)

Requires `require_admin_mode`. Aggregates and deduplicates all proposed new tags and suggested album paths across all non-duplicate items staged in the session.

```
GET /api/uploads/sessions/{session_id}/pending
```

**Response:**

```json
{
  "pending_tags": [
    {
      "name": "new_character",
      "category": "character",
      "used_by": ["d4a79fc539df"],
      "merge_into": null,
      "user_assigned": true
    }
  ],
  "pending_albums": [
    {
      "path": "Series/Vol1",
      "used_by": ["d4a79fc539df", "b91fc539df12"]
    }
  ]
}
```

---

### Update pending tag globally

Requires `require_admin_mode`. Updates a pending new tag across all items in the session that reference it (rename, change category, merge into another tag, or remove).

```
PATCH /api/uploads/sessions/{session_id}/pending/tags/{tag_name}
Content-Type: application/json

{
  "new_name": "renamed_character",
  "category": "character",
  "merge_into": null,
  "remove": false
}
```

| Field | Type | Description |
|---|---|---|
| `new_name` | string | Optional new name for the tag |
| `category` | string | Optional category update (`general`, `artist`, `character`, `copyright`, `meta`) |
| `merge_into` | string | Optional existing or new tag name to merge this tag into |
| `remove` | bool | Optional (default: `false`). When `true`, removes the tag from all staged items |

**Response:**

```json
{
  "status": "updated",
  "affected_items": 2
}
```

---

### Commit upload session

Requires `require_admin_mode`. Executes an atomic database transaction that finalizes the entire staging session into the library:

1. Creates confirmed new tags in the database.
2. Resolves and builds the album hierarchy for any `suggested_album_path` values.
3. Moves staged files to `ORIGINAL_DIR` under unique filenames.
4. Performs automated transcoding for formats requiring it (e.g. MKV/AVI to MP4, HEIC/JXL to WebP).
5. Generates production thumbnails in `THUMBNAIL_DIR`.
6. Inserts `Media` records, links tags and albums, and updates tag post counts and album timestamps.
7. Deletes the temporary session directory and cached thumbnails.

```
POST /api/uploads/sessions/{session_id}/commit
```

**Response:** `UploadSessionCommitResponse`

```json
{
  "results": [
    {
      "item_id": "d4a79fc539df",
      "filename": "artwork.png",
      "media_id": 142,
      "status": "created",
      "error": null
    }
  ],
  "total_created": 1,
  "total_duplicates": 0,
  "total_failed": 0
}
```
