## Admin: Authentication & Account

**Base path:** `/api/admin`

### Login

```
POST /api/admin/login
Content-Type: application/json

{ "username": "admin", "password": "..." }
```

Sets `admin_token` (HttpOnly JWT) and `admin_mode=true` cookies. Also returns the token in the JSON body.

### Logout

```
POST /api/admin/logout
```

Clears `admin_token` and `admin_mode` cookies.

### Toggle admin mode

```
POST /api/admin/toggle-admin-mode?enabled=true
```

Requires a valid session (JWT). Sets or removes the `admin_mode` cookie without re-authenticating.

### Update password

Requires `require_admin_mode`.

```
POST /api/admin/update-admin-password
Content-Type: application/json

{ "new_password": "..." }
```

Min length: 6, max length: 50.

### Update username

Requires `require_admin_mode`.

```
POST /api/admin/update-admin-username
Content-Type: application/json

{ "new_username": "newname" }
```

Re-issues the JWT cookie with the new username.
