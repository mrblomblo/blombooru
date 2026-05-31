## AI Tagger

> [!NOTE]
> Last updated: `May 31, 2026`

**Base path:** `/api/ai-tagger`

Uses the WDv3 model family to suggest tags for images. The `GET /api/ai-tagger/status` endpoint is public; all others require `require_admin_mode`.

### Available models

| Model | Approx. size |
|---|---|
| `wd-eva02-large-tagger-v3` (default) | ~850 MB |
| `wd-vit-tagger-v3` | ~350 MB |
| `wd-swinv2-tagger-v3` | ~450 MB |
| `wd-convnext-tagger-v3` | ~350 MB |
| `wd-vit-large-tagger-v3` | ~1200 MB |

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

### Get tagger settings

```
GET /api/ai-tagger/settings
```

**Response:** Current saved thresholds and model name, blacklisted tags, and `available_models`.

---

### Save tagger settings

```
PUT /api/ai-tagger/settings
Content-Type: application/json

{
  "general_threshold": 0.35,
  "character_threshold": 0.85,
  "model_name": "wd-eva02-large-tagger-v3",
  "blacklisted_tags": ["rating:general", "rating:sensitive"]
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
  "download_size_mb": 850,
  "optimal_batch_size": 8
}
```

---

### Download a model

Downloads and loads the specified model from HuggingFace Hub (blocking).

```
POST /api/ai-tagger/download/{model_name}
```

**Response:** `{ "success": true, "model": "...", "optimal_batch_size": 8, "message": "..." }`

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
