# Internal API Reference

> [!WARNING]
> **Stability notice:** The internal API has no stability guarantees and may change at any time without prior notice. Its intended use case is internal tooling. The docs are also not guaranteed to be up to date with the latest changes in the API.

> [!NOTE]
> Last updated: `October 9, 2026`  
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
  "language": { "id": "en", "name": "English", "native_name": "English" },
  "keybindings": { /* Action keybinding specifications */ },
  "supported_formats": { /* FormatRegistry mapping extensions to metadata */ }
}
```

The `auth_required` field corresponds to the `REQUIRE_AUTH` setting. When it is `true`, Layer 1 authentication (see below) is active and most endpoints will reject unauthenticated requests. When it is `false`, public read access is open and only write endpoints enforce credentials.

---

## Authentication

Authentication in blombooru operates across **two complementary layers**:

1. **Request Authentication (Layer 1)**: Middleware-level access gate that protects non-public routes when `REQUIRE_AUTH` is enabled.
2. **Endpoint Authorization and Admin Mode (Layer 2)**: Route-level dependencies that authenticate identity, enforce API key permission tiers, and apply UI safety toggles.

---

### Layer 1: Request Authentication (middleware)

This layer is enforced by the middleware and is **only active when `REQUIRE_AUTH` is `true`** in settings. When active, it validates every non-public request and returns `401 {"detail": "Authentication required"}` if no valid credential is found. When `REQUIRE_AUTH` is `false`, all requests pass through this layer; route dependencies still enforce Layer 2.

Accepted credential types:

| Method | Header / parameter |
|---|---|
| API key as Bearer token | `Authorization: Bearer blom_<key>` |
| API key as raw header | `Authorization: blom_<key>` |
| API key as query param | `?api_key=blom_<key>` *(API and Danbooru routes only)* |
| API key via HTTP Basic Auth | `Authorization: Basic base64(<user>:<blom_key>)` *(API and Danbooru routes only)* |
| JWT as Bearer token | `Authorization: Bearer <jwt>` |
| JWT as `admin_token` cookie | `Cookie: admin_token=<jwt>` |

> [!NOTE]
> API keys are strictly passed via headers or query parameters. Any `blom_` key provided in the `admin_token` cookie is rejected, as this cookie is reserved exclusively for browser JWT sessions.

---

### Layer 2: Endpoint Authorization and Admin Mode (route dependencies)

Regardless of the `REQUIRE_AUTH` setting, protected route dependencies always verify credentials, returning `401 {"detail": "Not authenticated"}` if unauthenticated:

- **`require_admin_mode` endpoints**: Write and content-mutation endpoints, including most of `/api/admin/*` (backups, API key management).
  - **API Keys**: Checked against their permission tier (see below). No `admin_mode` cookie is needed.
  - **Browser Sessions (`admin_token` cookie)**: The `admin_mode` cookie must be present and set to `"true"`. Without it, the endpoint returns `403 {"detail": "You need to be logged in as the admin to perform this action"}`. This is a UX safeguard against accidental destructive actions in the web UI.
  - **Bearer JWT**: Without an `admin_token` cookie, a Bearer JWT is not subject to the `admin_mode` toggle. The toggle is only enforced when the `admin_token` cookie is present.
- **`get_current_admin_user` endpoints**: Authentication and the API key tier check only. The `admin_mode` toggle is not checked.

---

### API Key Permission Tiers

API keys are assigned one of three permission tiers upon creation. The tier is enforced by request path, identically for both dependencies above: `/api/admin/*` requires an `admin` key, and all other protected routes require a `write` or `admin` key.

| Permission | Allowed Scope | Restrictions |
|---|---|---|
| `read` | Read-only access (search, viewing media, listing tags and albums) | Content mutation endpoints return `403 Forbidden` ("This API key has read-only access"); administrative endpoints under `/api/admin/*` return `403 Forbidden` ("This API key requires administrator access") |
| `write` | Content mutations (uploading, editing, tagging, deleting media and albums) | Administrative endpoints under `/api/admin/*` return `403 Forbidden` ("This API key requires administrator access") |
| `admin` | Full administrator privileges | No restrictions; can call `/api/admin/*` administrative endpoints and execute all operations |

---

### How to authenticate from a script

**Option 1: API Key (recommended for automation)**

Supply a `write` or `admin` API key via the `Authorization` header. Note that a `write` key cannot call `/api/admin/*` management endpoints (which require an `admin` key; see the permission tiers table above). No session cookies or `admin_mode` toggles are needed:

```bash
curl --request PATCH \
     --url http://127.0.0.1:8000/api/media/1 \
     --header 'Authorization: Bearer blom_<key>' \
     --header 'Content-Type: application/json' \
     --data '{"rating":"safe","description":"..."}'
```

**Option 2: Session cookie jar**

Log in once to obtain session cookies and reuse the resulting cookie jar. This satisfies browser session auth and the `admin_mode` toggle automatically:

```bash
# Step 1: login, save cookies to file
curl --cookie-jar cookies.txt \
     --request POST \
     --url http://127.0.0.1:8000/api/admin/login \
     --header 'Content-Type: application/json' \
     --data '{"username":"admin","password":"yourpassword"}'

# Step 2: use saved cookies for subsequent requests
curl --cookie cookies.txt \
     --request PATCH \
     --url http://127.0.0.1:8000/api/media/1 \
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

### Supported Formats and Transcoding

Blombooru maintains a centralized format registry. Supported media containers and codecs are handled either natively or through automated transcoding:

- **Native images:** `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.avif`, `.jxl`, `.bmp`, `.tiff`, `.tif`
- **Transcoded images:** `.heic`, `.heif` (automatically transcoded to `.webp`)
- **Native videos:** `.mp4`, `.webm`, `.mov`, `.m4v`
- **Transcoded videos:** `.mkv`, `.avi` (automatically transcoded to H.264/AAC `.mp4`)
- **Archives:** `.zip`, `.tar.gz`, `.tgz`, `.tar`
- **Themes:** `.blombooru-theme`, `.css`
- **Data & documents:** `.csv`, `.json`, `.txt`

When media requiring transcoding is uploaded or imported, the transcoded version is saved to `media/transcoded/` and served by default for in-browser playback and preview, while original files remain preserved for download.

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
| **Tags** | Tag listing, related tags, autocomplete, suggestions | [Tags](/docs/Internal%20API/API/Tags.md) |
| **Updates** | System update and release checking | [Updates](/docs/Internal%20API/API/Updates.md) |
| **Upload Sessions** | Staging sessions, file review, and atomic upload commit | [Upload Sessions](/docs/Internal%20API/API/Upload%20Sessions.md) |
| **URL Import** | Probe, proxy, and import media from direct URLs or boorus | [URL Import](/docs/Internal%20API/API/URL%20Import.md) |
| **Admin: API Keys** | API key generation and management | [Admin/API Management](/docs/Internal%20API/API/Admin/API%20Management.md) |
| **Admin: Auth & Account** | Admin login, admin mode, credentials | [Admin/Auth and Account](/docs/Internal%20API/API/Admin/Auth%20and%20Account.md) |
| **Admin: Backup & Import** | Tag/media export and full backup import | [Admin/Backup](/docs/Internal%20API/API/Admin/Backup.md) |
| **Admin: Custom Themes** | Custom theme CRUD and import/export | [Admin/Custom Themes](/docs/Internal%20API/API/Admin/Custom%20Themes.md) |
| **Admin: Media** | Untracked file scanning, stats, and thumbnail management | [Admin/Media](/docs/Internal%20API/API/Admin/Media.md) |
| **Admin: Settings** | App configuration, cache management, themes, languages | [Admin/Settings](/docs/Internal%20API/API/Admin/Settings.md) |
| **Admin: Shared Tags** | Shared tag database sync and status | [Admin/Shared Tags](/docs/Internal%20API/API/Admin/Shared%20Tags.md) |
| **Admin: Tags Management** | Tag CSV imports, bulk operations | [Admin/Tags](/docs/Internal%20API/API/Admin/Tags.md) |
