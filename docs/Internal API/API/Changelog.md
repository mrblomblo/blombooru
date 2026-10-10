## Changelog

> [!NOTE]
> Last updated: `October 10, 2026`

**Base path:** `/api/changelog`

All changelog endpoints require `require_admin_mode`.

### Get changelog status and content

```
GET /api/changelog
```

Checks whether the "What's Changed" modal should be presented to the administrator after an update and returns pre-rendered HTML of the release notes parsed from `CHANGELOG.md`.

- If `LAST_SEEN_VERSION` matches the current `APP_VERSION`, returns `needs_modal: false`.
- On a fresh installation where no previous version was recorded, the current version is silently marked as seen and returns `needs_modal: false`.
- If an update occurred, version headings are automatically converted into GitHub release links and rendered into HTML.

**Response:**

```json
{
  "needs_modal": true,
  "current_version": "1.40.0",
  "html": "<div class=\"changelog-version bg p-3 md:p-4 border\">...</div>"
}
```

### Acknowledge changelog

```
POST /api/changelog/acknowledge
```

Marks the current application version as acknowledged by updating `last_seen_version` in `settings.json`.

**Response:**

```json
{
  "ok": true
}
```
