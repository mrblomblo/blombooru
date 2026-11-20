## Admin: Maintenance

> [!NOTE]
> Last updated: `November 20, 2026`

**Base path:** `/api/admin/maintenance`

All endpoints require `require_admin_mode`.

Endpoints for querying the status of background admin maintenance jobs.

---

### Get all maintenance job statuses

Requires `require_admin_mode`. Returns summary status objects for all registered maintenance jobs (including `transcode_media` and `near_duplicate_backfill`). Large `result` payloads are omitted from the summary; query the per-job endpoint to retrieve them.

```
GET /api/admin/maintenance/status
```

**Response:**

```json
{
  "jobs": {
    "generate_missing_thumbnails": {
      "running": false,
      "current": 0,
      "total": 0,
      "current_file": null,
      "error": null,
      "started_at": null,
      "finished_at": null,
      "orphans_deleted": 0,
      "generated": 0,
      "failed": 0,
      "skipped": 0
    },
    "regenerate_all_thumbnails": { "running": false, "..." : "..." },
    "relink_media": { "running": false, "..." : "..." },
    "transcode_media": { "running": false, "..." : "..." },
    "near_duplicate_backfill": { "running": false, "..." : "..." },
    "apply_aliases": { "running": false, "..." : "..." },
    "apply_implications": { "running": false, "..." : "..." },
    "backfill_implied_tags": { "running": false, "..." : "..." },
    "apply_tag_ratings": { "running": false, "..." : "..." },
    "recalculate_album_metrics": { "running": false, "..." : "..." },
    "prune_albums": { "running": false, "..." : "..." }
  }
}
```

---

### Get single maintenance job status

Requires `require_admin_mode`. Returns detailed status for a single maintenance job, including `result` (or `last_result` for `transcode_media`) once completed.

```
GET /api/admin/maintenance/status/{job_name}
```

**Supported `job_name` values:**

- `generate_missing_thumbnails`
- `regenerate_all_thumbnails`
- `relink_media`
- `transcode_media`
- `near_duplicate_backfill`
- `apply_aliases`
- `apply_implications`
- `backfill_implied_tags`
- `apply_tag_ratings`
- `recalculate_album_metrics`
- `prune_albums`

**Response:**

```json
{
  "running": false,
  "current": 120,
  "total": 120,
  "current_file": null,
  "error": null,
  "result": {
    "orphans_deleted": 2,
    "generated": 5,
    "failed": 0,
    "skipped": 115,
    "total": 120
  },
  "started_at": 1763580000.12,
  "finished_at": 1763580004.56
}
```

Returns `404` (`Unknown maintenance job`) if `job_name` is not recognized.
