## Updates

**Base path:** `/api/system`

All endpoints require `require_admin_mode`.

### Check for updates

```
GET /api/system/update/check
```

Queries the GitHub Releases API and compares the latest release tag against the running version.

**Response:** `UpdateStatus` object with fields including `current_version`, `latest_version`, `update_available`, `releases`, `commits`, `config_files_changed`, etc.

### Perform update

```
POST /api/system/update/perform
Content-Type: application/json

{ "target": {} }
```

Only supported for local (non-Docker) deployments. Runs `git fetch --tags && git checkout <latest_tag>` and reinstalls Python dependencies if `requirements.txt` changed.
