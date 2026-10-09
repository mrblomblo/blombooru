import ipaddress
import socket
from urllib.parse import urlparse

class UrlValidationError(Exception):
    """Raised when a URL fails security validation."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)

def validate_url_not_ssrf(url: str) -> None:
    """
    Resolve the hostname in url to an IP address and reject any address that
    falls within a private, loopback, link-local, or otherwise reserved range.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise UrlValidationError("invalid_url")

    hostname = parsed.hostname
    if not hostname:
        raise UrlValidationError("invalid_url")

    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        from ..config import settings
        if settings.BOORU_PROXY_URL:
            return
        raise UrlValidationError("invalid_url")

    for _family, _type, _proto, _canonname, sockaddr in addrinfos:
        raw_ip = sockaddr[0]
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            raise UrlValidationError("invalid_url")

        if (
            not ip.is_global
            or ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UrlValidationError("ssrf_blocked")


def is_safe_return_url(url: str | None) -> bool:
    """
    Validate that a return URL is a safe relative path.
    Enforces that return_url starts with a single '/' and not '//' or '/\\',
    and contains no ASCII control characters.
    """
    if not url or not isinstance(url, str):
        return False

    # Must start with a single '/' and not '//' or '/\'
    if not url.startswith("/") or url.startswith(("//", "/\\")):
        return False

    # Reject ASCII control characters (which browsers strip or normalize)
    if any(ord(c) < 32 or ord(c) == 127 for c in url):
        return False

    return True


def get_safe_return_url(url: str | None, default: str = "/") -> str:
    """
    Return url if it is safe, otherwise return default.
    """
    if is_safe_return_url(url):
        return url
    return default
