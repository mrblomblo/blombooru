# Security

Keeping your personal media collection safe and private is important! Blombooru is designed primarily as a **single-user, self-hosted** application. While it includes robust authentication and access controls, it is not hardened for public internet exposure in the same way a large multi-tenant SaaS product would be.

Before you expose your instance to the wild web (e.g., via a reverse proxy), please read through these security considerations to ensure your data stays protected.

## Deployment Considerations

### Reverse Proxy

If Blombooru sits behind a reverse proxy (like Nginx, Caddy, or Traefik), keep the following in mind:

- **Set `X-Forwarded-For` correctly.** Blombooru uses this header for login rate limiting. Your proxy should completely overwrite (not just append to) this header with the real client IP. If this is misconfigured, attackers could spoof their IP address to bypass rate limits!
- **Use HTTPS.** The authentication cookie is set with the `Secure` flag only when the request scheme is HTTPS. Without HTTPS, the cookie will be transmitted in plaintext, leaving it vulnerable to interception.

### API Keys

Blombooru supports three ways to pass API keys when integrating with third-party tools:

1. **`Authorization: Bearer blom_...`** header (Recommended)
2. **HTTP Basic Auth** with the API key as the password (for Danbooru client compatibility)
3. **`?api_key=blom_...`** query parameter (for Danbooru client compatibility)

> [!IMPORTANT]
> If possible, prefer method 1 or 2! Method 3 exists specifically for compatibility with third-party Danbooru clients that require it.

If you must use method 3, be aware that your API key is sent directly in the URL and will appear in:
- Server access logs
- Browser history
- Reverse proxy logs
- HTTP `Referer` headers sent to external sites

> [!NOTE]
> API keys are stored as SHA-256 hashes in the database. Only the key prefix (e.g., `blom_abcd12`) is stored in plaintext so it can be identified in the UI. The full key is shown only once at creation time!

### Authentication Modes

The security level of your instance is determined by the `REQUIRE_AUTH` setting:

- **`REQUIRE_AUTH=true`**: All routes require authentication. This includes Danbooru API routes, which will strictly require valid credentials. Perfect for keeping your collection entirely private.
- **`REQUIRE_AUTH=false`** (Default): The web UI and API are accessible to anyone without logging in. Danbooru API routes are also fully open. However, all administrative actions (uploading, editing, deleting) still require admin authentication.

### Admin mode

The `admin_mode` cookie is a **UI safety toggle**, not a security mechanism. It prevents accidental destructive actions (like deleting media) when you are not actively managing your library. Actual authentication for admin endpoints is enforced via JWT token validation. See the docstrings on `is_admin_mode` and `require_admin_mode` in `backend/app/auth.py` for details.

### Debug Mode

When troubleshooting, you might be tempted to turn on debug mode (`BLOMBOORU_DEBUG=true`). In this mode, HTTP error responses will include full exception messages, including stack traces, file paths, and database details.

> [!WARNING]
> **Do not run debug mode on a publicly accessible instance!** This exposes sensitive internal information that an attacker could use to compromise your server.

## Reporting Vulnerabilities

If you discover a security vulnerability, please help make Blombooru safer! Open a new GitHub issue or contact the maintainer directly. 

> [!NOTE]
> There is currently no bug bounty program, but your contributions to the project's security are greatly appreciated!
