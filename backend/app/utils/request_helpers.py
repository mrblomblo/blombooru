from ..config import settings

def safe_error_detail(description: str, error: Exception) -> str:
    """Return an error detail string for HTTP responses.
    
    In DEBUG mode, includes the full exception message for debugging.
    In production, returns only the generic description to avoid leaking
    internal details (paths, hostnames, stack traces, etc.).
    """
    if settings.DEBUG:
        return f"{description}: {str(error)}"
    return description

def get_client_ip(request) -> str:
    """Extract the client IP from a request.
    
    Uses the first entry from X-Forwarded-For if present (set by reverse
    proxies), otherwise falls back to request.client.host.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
