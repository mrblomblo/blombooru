## Acknowledgements

> [!NOTE]
> Last updated: `October 10, 2026`

**Base path:** `/api/acknowledgements`

### Get acknowledgements

No auth required.

```
GET /api/acknowledgements
```

Parses `ACKNOWLEDGEMENTS.md` and returns structured, pre-rendered HTML cards containing license and attribution details for all open-source libraries and dependencies used by blombooru. Content is cached in memory and invalidated automatically when `ACKNOWLEDGEMENTS.md` modification time changes.

**Response:**

```json
{
  "html": "<div class=\"acknowledgement-preamble bg p-3 md:p-4 border mb-4 text-sm\">...</div><div class=\"acknowledgement-card bg p-3 md:p-4 border space-y-2\" data-pkg-name=\"fastapi\">...</div>"
}
```
