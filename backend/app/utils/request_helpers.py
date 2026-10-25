import ipaddress
import os

from ..config import settings, _parse_trusted_proxies

def safe_error_detail(description: str, error: Exception) -> str:
    """Return an error detail string for HTTP responses.
    
    In DEBUG mode, includes the full exception message for debugging.
    In production, returns only the generic description to avoid leaking
    internal details (paths, hostnames, stack traces, etc.).
    """
    if settings.DEBUG:
        return f"{description}: {str(error)}"
    return description

def _parse_ip(s: str):
    """Parse *s* as an IP address, normalising IPv4-mapped IPv6 to IPv4."""
    try:
        addr = ipaddress.ip_address(s)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            return addr.ipv4_mapped
        return addr
    except ValueError:
        return None

def get_client_ip(request) -> str:
    """Extract the client IP from a request."""
    trusted = _parse_trusted_proxies(
        os.getenv("BLOMBOORU_TRUSTED_PROXIES", "").strip()
    )

    if trusted:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            xff_addrs = [a.strip() for a in forwarded_for.split(",") if a.strip()]
            direct_peer = request.client.host if request.client else None
            chain = xff_addrs + ([direct_peer] if direct_peer else [])

            # Walk right-to-left, skipping trusted proxy addresses.
            for addr in reversed(chain):
                ip = _parse_ip(addr)
                if ip is None:
                    break
                if any(ip in net for net in trusted):
                    continue
                return str(ip)

    if request.client:
        peer = _parse_ip(request.client.host)
        return str(peer) if peer is not None else request.client.host
    return "unknown"
