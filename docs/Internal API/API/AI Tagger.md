## AI Tagger

> [!NOTE]
> Last updated: `October 10, 2026`

**Base path:** `/api/ai-tagger`

Uses the WDv3 model family to suggest tags for images. The `GET /api/ai-tagger/status` endpoint is public; all others require `require_admin_mode`.

### Available models

| Model | Approx. size | Speed Rank (CPU) | Accuracy Rank | Optimal Batch Size (CPU) |
|---|---|---|---|---|
| `pixai-tagger-v1.0` | ~935 MB | 6 (Slowest) | 1 (Most accurate) | 1 |
| `wd-eva02-large-tagger-v3` (default) | ~850 MB | 4 | 2 | 2 |
| `wd-vit-large-tagger-v3` | ~1200 MB | 5 | 3 | 5 |
| `wd-swinv2-tagger-v3` | ~450 MB | 3 | 4 | 15 |
| `wd-convnext-tagger-v3` | ~350 MB | 2 | 5 | 1 |
| `wd-vit-tagger-v3` | ~350 MB | 1 (Fastest) | 6 (Least accurate) | 10 |

---

### Get tagger status

No auth required.

```
GET /api/ai-tagger/status
```

**Response:**

```json
{
  "available": true,
  "loaded": false,
  "current_model": null,
  "available_models": ["wd-eva02-large-tagger-v3", "..."]
}
```

`available: false` means the optional dependencies are not installed.

---

### Get available models

Requires `require_admin_mode`. Returns the list of models sorted by `accuracy_rank` ascending.

```
GET /api/ai-tagger/models
```

**Response:**

```json
[
  {
    "name": "pixai-tagger-v1.0",
    "repo_id": "A1yCE/pixai-tagger-v1.0-onnx-fp16",
    "is_downloaded": true,
    "is_loaded": false,
    "is_downloading": false,
    "speed_rank": 6,
    "accuracy_rank": 1
  },
  {
    "name": "wd-eva02-large-tagger-v3",
    "repo_id": "SmilingWolf/wd-eva02-large-tagger-v3",
    "is_downloaded": true,
    "is_loaded": false,
    "is_downloading": false,
    "speed_rank": 4,
    "accuracy_rank": 2
  }
]
```

---

### Get tagger settings

```
GET /api/ai-tagger/settings
```

**Response:** Current saved thresholds and model name, `blacklisted_tags`, `blacklisted_categories`, and `available_models`.

---

### Save tagger settings

```
PUT /api/ai-tagger/settings
Content-Type: application/json

{
  "general_threshold": 0.35,
  "character_threshold": 0.85,
  "model_name": "wd-eva02-large-tagger-v3",
  "blacklisted_tags": ["rating:general", "rating:sensitive"],
  "blacklisted_categories": ["meta"]
}
```

All fields are optional. Settings are persisted to `settings.json`.

---

### Get model download / load status

```
GET /api/ai-tagger/model-status/{model_name}
```

**Response:** `ModelStatusResponse`

```json
{
  "model_name": "wd-eva02-large-tagger-v3",
  "is_downloaded": true,
  "is_loaded": false,
  "is_downloading": false,
  "download_size_mb": 850,
  "optimal_batch_size": 2
}
```

---

### Download a model

Requires `require_admin_mode`. Initiates download and loading of the specified model from HuggingFace Hub with real-time SSE progress streaming.

```
POST /api/ai-tagger/download/{model_name}
```

**Response:** `text/event-stream`. Each `data:` line is a JSON object.

The stream emits `progress` events during download and terminates with a `complete`, `cancelled`, or `error` event:

```json
{
  "type": "progress",
  "filename": "model.onnx",
  "file_index": 0,
  "file_downloaded_bytes": 10485760,
  "file_total_bytes": 850000000,
  "downloaded_bytes": 10485760,
  "total_bytes": 850000000,
  "percent": 1.2,
  "speed_bps": 5242880.0,
  "elapsed_seconds": 2.0
}
```

- `percent` can be `null` if total file size cannot be determined.

Terminal stream events:

```json
{
  "type": "complete",
  "model": "wd-eva02-large-tagger-v3",
  "optimal_batch_size": 2,
  "message": "Model wd-eva02-large-tagger-v3 downloaded and loaded successfully"
}
```
```json
{ "type": "cancelled" }
```
```json
{ "type": "error", "error": "Connection error" }
```

---

### Cancel model download

Requires `require_admin_mode`. Cancels an active download for a specific model.

```
POST /api/ai-tagger/download/{model_name}/cancel
```

**Response:** `{ "success": true }`

---

### Cancel all active downloads

Requires `require_admin_mode`. Cancels all in-progress model downloads.

```
POST /api/ai-tagger/cancel-download
```

**Response:** `{ "success": true }`

---

### Delete downloaded model

Requires `require_admin_mode`. Deletes a downloaded model from local cache and unloads it from memory if currently loaded.

```
DELETE /api/ai-tagger/model/{model_name}
```

**Response (200 OK):** `{ "success": true, "model_name": "wd-eva02-large-tagger-v3" }`

**Possible errors:**
- `400 Bad Request`: Unknown model name.
- `404 Not Found`: Model is not downloaded locally.
- `409 Conflict`: Cannot delete a model that is currently downloading.
- `503 Service Unavailable`: AI Tagger dependencies are not installed.

---

### Pre-load a model

```
POST /api/ai-tagger/load?model_name=wd-eva02-large-tagger-v3
```

Loads the model into memory without running inference. Useful for warming up before a bulk tagging session.

---

### Predict tags for a single media item

```
POST /api/ai-tagger/predict/{media_id}
Content-Type: application/json

{
  "general_threshold": 0.35,
  "character_threshold": 0.85,
  "hide_rating_tags": true,
  "character_tags_first": true,
  "model_name": "wd-eva02-large-tagger-v3"
}
```

All body fields are optional (defaults shown above).

**Response:** `PredictTagsResponse`

```json
{
  "media_id": 1,
  "tags": [
    { "name": "fox", "category": "general", "confidence": 0.92 }
  ],
  "model_used": "wd-eva02-large-tagger-v3"
}
```

Tags in the saved blacklist are automatically filtered out of the results.

---

### Predict tags for multiple media items (batch)

```
POST /api/ai-tagger/predict-batch
Content-Type: application/json

{
  "media_ids": [1, 2, 3],
  "general_threshold": 0.35,
  "character_threshold": 0.85,
  "hide_rating_tags": true,
  "character_tags_first": true,
  "model_name": "wd-eva02-large-tagger-v3"
}
```

Maximum batch size: 200 items.

**Response:** `BatchPredictResponse`

```json
{
  "results": [ /* PredictTagsResponse[] */ ],
  "failed_ids": [99],
  "model_used": "wd-eva02-large-tagger-v3",
  "processing_time_ms": 1234.5
}
```

---

### Predict tags (streaming, Server-Sent Events)

Streams results one by one as they complete, without waiting for the whole batch.

```
POST /api/ai-tagger/predict-stream
Content-Type: application/json

{ "media_ids": [1, 2, 3], ... }
```

**Response:** `text/event-stream`. Each `data:` line is a JSON object:

```json
{ "type": "result", "media_id": 1, "tags": [...], "progress": 1, "total": 3 }
{ "type": "error",  "media_id": 99, "error": "File not found" }
{ "type": "complete", "total": 2 }
```
