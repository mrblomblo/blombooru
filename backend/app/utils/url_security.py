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
        raise UrlValidationError("invalid_url")

    for _family, _type, _proto, _canonname, sockaddr in addrinfos:
        raw_ip = sockaddr[0]
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            raise UrlValidationError("invalid_url")

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UrlValidationError("ssrf_blocked")
