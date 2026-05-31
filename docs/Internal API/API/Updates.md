## Updates

> [!NOTE]
> Last updated: `May 31, 2026`

**Base path:** `/api/system`

All endpoints require `require_admin_mode`.

### Check for updates

```
GET /api/system/update/check
```

Queries the GitHub Releases API and compares the latest release tag against the running version.

**Response:** `UpdateStatus` object with the following fields:

| Field | Description |
|---|---|
| `current_version` | Running version string |
| `latest_version` | Latest tagged release on GitHub |
| `update_available` | `true` when a newer version exists |
| `releases` | Array of `ReleaseInfo` objects (tag, name, body, url) newer than the current version |
| `commits` | Array of `CommitInfo` objects (hash, message) between current and latest |
| `config_files_changed` | `true` if any of `docker-compose.yml`, `example.env`, etc. changed |
| `changed_config_files` | List of changed config filenames |
| `asset_urls` | Download URLs for changed config files from the release assets |
| `deployment_type` | `"local"`, `"ghcr"`, or `"docker_local"` |
| `notices` | Array of i18n key strings with deployment-specific warnings |

Returns `429` if the GitHub API rate limit is exceeded, or `502` if GitHub is unreachable.

### Perform update

```
POST /api/system/update/perform
Content-Type: application/json

{ "target": {} }
```

> [!IMPORTANT]
> Only supported for `local` (direct Python) deployments. Docker deployments (`ghcr` or `docker_local`) are rejected with `400` and instructed to update via `docker compose` on the host.

For local deployments, runs `git fetch --tags && git checkout <latest_tag>`. If `requirements.txt` changed, dependencies are automatically reinstalled.

**Response:**

```json
{
  "success": true,
  "log": "...",
  "message": "Update successful. Please restart Blombooru to apply the changes!",
  "actions_taken": {
    "git_updated": true,
    "dependencies_installed": false,
    "needs_restart": true
  }
}
```
