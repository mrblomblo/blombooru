# Internal API Reference

> [!WARNING]
> **Stability notice:** The internal API has no stability guarantees and may change at any time without prior notice. Its intended use case is internal tooling. The docs are also not guaranteed to be up to date with the latest changes in the API.

> [!NOTE]
> Last updated: `June 1, 2026`  
> Update date for the docs can be found in the individual doc files.


All endpoints are served under the same origin as the blombooru web UI. JSON is returned by default; requests that accept a request body expect `Content-Type: application/json` unless noted otherwise.

---

## Instance Discovery

Before doing anything else, call the instance-info endpoint. It is **always public** (no authentication required) and tells you everything a client needs to bootstrap. See the [Instance Info](/docs/Internal%20API/API/Instance%20Info.md) documentation for full details on the response payload.

```
GET /api/instance-info
```

```json
{
  "app_name": "Blombooru",
  "app_version": "1.40.0",
  "auth_required": false,
  "theme": { /* ThemeMetadata with backup theme */ },
  "language": { "id": "en", "name": "English", "native_name": "English" }
}
```

The `auth_required` field corresponds to the `REQUIRE_AUTH` setting. When it is `true`, Layer 1 authentication (see below) is active and most endpoints will reject unauthenticated requests. When it is `false`, public read access is open and only write endpoints enforce credentials.

---

## Authentication

Authentication in blombooru operates across **two independent layers**. Both must be satisfied to successfully call write endpoints from a script.

---

### Layer 1: Request Authentication (middleware)

This layer is enforced by the middleware and is **only active when `REQUIRE_AUTH` is `true`** in settings. When active, it validates every non-public request and returns `401 {"detail": "Authentication required"}` if no valid credential is found. When `REQUIRE_AUTH` is `false`, all requests pass through unchecked at this layer.

Accepted credential types:

| Method | Header / parameter |
|---|---|
| API key as Bearer token | `Authorization: Bearer blom_<key>` |
| API key as raw header | `Authorization: blom_<key>` |
| API key as query param | `?api_key=blom_<key>` |
| API key via HTTP Basic Auth | `Authorization: Basic base64(<user>:<blom_key>)` |
| JWT as Bearer token | `Authorization: Bearer <jwt>` |
| JWT or API key as `admin_token` cookie | `Cookie: admin_token=<jwt>` |

> [!NOTE]
> `Authorization: Bearer <jwt>` authenticates you at the middleware level, but on its own is **not sufficient** for write endpoints. See Layer 2.

---

### Layer 2: Admin Mode (route dependency)

All write endpoints (marked `require_admin_mode` in this document) have an **unconditional** secondary check that is active regardless of `REQUIRE_AUTH` and regardless of how Layer 1 auth was provided.

This check requires the `admin_mode` cookie to be present and set to `"true"`. Without it the endpoint returns `403` even when a valid credential is supplied.

This is a UX safeguard against accidental destructive actions in the browser UI. **It is not a security gate**. For scripting purposes it must simply be passed as a cookie header.

---

### How to authenticate from a script

**Recommended: use the session cookie jar**

Log in once and reuse the resulting cookies. This is the simplest approach and satisfies both layers automatically.

```bash
# Step 1: login, save both cookies to file
curl --cookie-jar cookies.txt \
     --request POST \
     --url http://127.0.0.1:8000/api/admin/login \
     --header 'Content-Type: application/json' \
     --data '{"username":"admin","password":"yourpassword"}'

# Step 2: use saved cookies for any subsequent request
curl --cookie cookies.txt \
     --request PATCH \
     --url http://127.0.0.1:8000/api/media/1 \
     --header 'Content-Type: application/json' \
     --data '{"rating":"safe","description":"..."}'
```

**Alternative: API key + admin_mode cookie**

If you have an API key and prefer not to use a session, you must still supply the `admin_mode` cookie manually for write endpoints:

```bash
curl --request PATCH \
     --url http://127.0.0.1:8000/api/media/1 \
     --header 'Authorization: Bearer blom_<key>' \
     --header 'Cookie: admin_mode=true' \
     --header 'Content-Type: application/json' \
     --data '{"rating":"safe","description":"..."}'
```

---

### Obtaining a JWT via Login

```http
POST /api/admin/login
Content-Type: application/json

{
  "username": "admin",
  "password": "yourpassword"
}
```

**Response:**

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

The login endpoint also sets `admin_token=<jwt>` (HttpOnly) and `admin_mode=true` as cookies. JWTs expire after 30 days.

**Rate limiting:** The login endpoint applies a per-IP rate limit on failed attempts.

---

## Common Types

| Type | Values |
|---|---|
| **Rating** | `"safe"` \| `"questionable"` \| `"explicit"` |
| **Tag Category** | `"general"` \| `"artist"` \| `"character"` \| `"copyright"` \| `"meta"` |
| **File Type** | `"image"` \| `"video"` \| `"gif"` |

---

## Error Responses

All error responses follow the FastAPI default format:

```json
{ "detail": "Human-readable error message" }
```

### Common Status Codes

| Code | Meaning | Notes |
|---|---|---|
| 400 | Bad request / validation error | |
| 401 | Missing or invalid credentials | `"Authentication required"` = Layer 1 rejection; `"Not authenticated"` = invalid credential |
| 403 | Authenticated but `admin_mode` not active | Layer 2 rejection; supply `Cookie: admin_mode=true` |
| 404 | Resource not found | |
| 409 | Conflict | e.g. duplicate media hash |
| 429 | Rate limited | Login endpoint only |
| 500 | Internal server error | |
| 502 | External service error | e.g. GitHub API or remote booru unreachable |

> [!NOTE]
> When `REQUIRE_AUTH` is `false`, Layer 1 is bypassed entirely. Layer 2 (`admin_mode=true` cookie) is always enforced for write endpoints regardless.

## API Endpoints

| Category | Description | Link |
|---|---|---|
| **Instance Info** | Harmless public metadata for clients | [Instance Info](/docs/Internal%20API/API/Instance%20Info.md) |
| **AI Tagger** | WDv3 model tag prediction | [AI Tagger](/docs/Internal%20API/API/AI%20Tagger.md) |
| **Albums** | Album management, contents, hierarchy | [Albums](/docs/Internal%20API/API/Albums.md) |
| **Booru Config** | External booru credentials | [Booru Config](/docs/Internal%20API/API/Booru%20Config.md) |
| **Booru Import** | Fetch and download posts from external boorus | [Booru Import](/docs/Internal%20API/API/Booru%20Import.md) |
| **Media** | Media listing, uploading, and updating | [Media](/docs/Internal%20API/API/Media.md) |
| **Search** | Tag-based search and random media | [Search](/docs/Internal%20API/API/Search.md) |
| **Shared Media** | Public endpoints for shared media links | [Shared Media](/docs/Internal%20API/API/Shared%20Media.md) |
| **Tag Implications** | Tag implication rules | [Tag Implications](/docs/Internal%20API/API/Tag%20Implications.md) |
| **Tags** | Tag listing, related tags, autocomplete | [Tags](/docs/Internal%20API/API/Tags.md) |
| **Updates** | System update and release checking | [Updates](/docs/Internal%20API/API/Updates.md) |
| **Admin: API Keys** | API key generation and management | [Admin/API Management](/docs/Internal%20API/API/Admin/API%20Management.md) |
| **Admin: Auth & Account** | Admin login, admin mode, credentials | [Admin/Auth and Account](/docs/Internal%20API/API/Admin/Auth%20and%20Account.md) |
| **Admin: Backup & Import** | Tag/media export and full backup import | [Admin/Backup](/docs/Internal%20API/API/Admin/Backup.md) |
| **Admin: Custom Themes** | Custom theme CRUD and import/export | [Admin/Custom Themes](/docs/Internal%20API/API/Admin/Custom%20Themes.md) |
| **Admin: Media** | Untracked file scanning, stats, and thumbnail management | [Admin/Media](/docs/Internal%20API/API/Admin/Media.md) |
| **Admin: Settings** | App configuration, instance info, themes, languages | [Admin/Settings](/docs/Internal%20API/API/Admin/Settings.md) |
| **Admin: Shared Tags** | Shared tag database sync and status | [Admin/Shared Tags](/docs/Internal%20API/API/Admin/Shared%20Tags.md) |
| **Admin: Tags Management** | Tag CSV imports, bulk operations | [Admin/Tags](/docs/Internal%20API/API/Admin/Tags.md) |
