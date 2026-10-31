import os
import unittest
from unittest.mock import MagicMock, patch

def _make_request(peer_host: str, xff: str | None = None):
    """Build a minimal mock FastAPI Request object."""
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = peer_host
    headers = {}
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    req.headers = headers
    return req

class TestGetClientIpNoTrustedProxies(unittest.TestCase):
    """When BLOMBOORU_TRUSTED_PROXIES is empty the header must be ignored."""

    def setUp(self):
        # Ensure the env var is absent.
        os.environ.pop("BLOMBOORU_TRUSTED_PROXIES", None)
        # Re-import after clearing the env.
        from backend.app.utils import request_helpers
        self.get_client_ip = request_helpers.get_client_ip

    def test_no_xff_returns_peer(self):
        req = _make_request("1.2.3.4")
        self.assertEqual(self.get_client_ip(req), "1.2.3.4")

    def test_xff_present_ignored_returns_peer(self):
        """The forged XFF header must be ignored; only the TCP peer counts."""
        req = _make_request("1.2.3.4", xff="9.9.9.9")
        self.assertEqual(self.get_client_ip(req), "1.2.3.4")

    def test_multi_hop_xff_ignored(self):
        req = _make_request("1.2.3.4", xff="203.0.113.5, 10.0.0.1")
        self.assertEqual(self.get_client_ip(req), "1.2.3.4")

    def test_no_client_returns_unknown(self):
        req = MagicMock()
        req.client = None
        req.headers = {}
        self.assertEqual(self.get_client_ip(req), "unknown")

    def test_no_client_with_xff_ignored_returns_unknown(self):
        req = MagicMock()
        req.client = None
        req.headers = {"X-Forwarded-For": "1.2.3.4"}
        self.assertEqual(self.get_client_ip(req), "unknown")

class TestGetClientIpWithTrustedProxies(unittest.TestCase):
    """When trusted proxies are configured the XFF chain is resolved safely."""

    def _get_ip(self, peer: str, xff, trusted: str):
        with patch.dict(os.environ, {"BLOMBOORU_TRUSTED_PROXIES": trusted}):
            from backend.app.utils import request_helpers
            req = _make_request(peer, xff=xff)
            return request_helpers.get_client_ip(req)

    def test_client_behind_one_trusted_proxy(self):
        # Topology: client(203.0.113.5) -> proxy(10.0.0.1) -> app
        ip = self._get_ip(
            peer="10.0.0.1",
            xff="203.0.113.5",
            trusted="10.0.0.0/8",
        )
        self.assertEqual(ip, "203.0.113.5")

    def test_client_behind_two_trusted_proxies(self):
        # client(5.5.5.5) -> proxy1(10.0.0.1) -> proxy2(10.0.0.2) -> app
        ip = self._get_ip(
            peer="10.0.0.2",
            xff="5.5.5.5, 10.0.0.1",
            trusted="10.0.0.0/8",
        )
        self.assertEqual(ip, "5.5.5.5")

    def test_walk_stops_at_first_untrusted_from_right(self):
        # client(10.0.0.1 -- trusted peer) injects an extra XFF entry.
        # Walk stops at "203.0.113.99" (first non-trusted address from right),
        # and does not return the forged leftmost entry.
        ip = self._get_ip(
            peer="10.0.0.1",
            xff="evil-forged.example, 203.0.113.99",
            trusted="10.0.0.0/8",
        )
        self.assertEqual(ip, "203.0.113.99")

    def test_all_chain_trusted_falls_back_to_peer(self):
        # Every address in the XFF chain is trusted; the direct peer is returned.
        ip = self._get_ip(
            peer="10.0.0.2",
            xff="10.0.0.1",
            trusted="10.0.0.0/8",
        )
        self.assertEqual(ip, "10.0.0.2")

    def test_ipv6_trusted_proxy(self):
        ip = self._get_ip(
            peer="::1",
            xff="2001:db8::1",
            trusted="::1",
        )
        self.assertEqual(ip, "2001:db8::1")

    def test_ipv4_mapped_ipv6_matches_ipv4_trusted_network(self):
        # ::ffff:10.0.0.5 is the IPv4-mapped form of 10.0.0.5.  It must be
        # recognised as trusted when 10.0.0.0/8 is in TRUSTED_PROXIES.
        ip = self._get_ip(
            peer="::ffff:10.0.0.1",
            xff="203.0.113.7",
            trusted="10.0.0.0/8",
        )
        self.assertEqual(ip, "203.0.113.7")

    def test_malformed_entry_in_chain_falls_back_to_peer(self):
        # A garbage string in the XFF chain cannot be parsed as an IP address.
        # The walk aborts and the function falls back to request.client.host.
        # This closes the junk-string rotation bypass.
        ip = self._get_ip(
            peer="10.0.0.1",
            xff="not-an-ip",
            trusted="10.0.0.0/8",
        )
        self.assertEqual(ip, "10.0.0.1")

    def test_no_xff_with_trusted_proxies_returns_peer(self):
        ip = self._get_ip(peer="1.2.3.4", xff=None, trusted="10.0.0.0/8")
        self.assertEqual(ip, "1.2.3.4")

    def test_invalid_trusted_proxies_entry_warns(self):
        import logging
        from backend.app.config import _parse_trusted_proxies
        _parse_trusted_proxies.cache_clear()
        try:
            with self.assertLogs("blombooru", level=logging.WARNING) as cm:
                nets = _parse_trusted_proxies("10.0.0.0/8,not-a-cidr")
            self.assertEqual(len(nets), 1)  # only the valid entry was kept
            self.assertTrue(any("not-a-cidr" in msg for msg in cm.output))
        finally:
            _parse_trusted_proxies.cache_clear()

    def test_invalid_entry_warns_only_once(self):
        """The warning fires once per distinct raw string, not on every call."""
        import logging
        from backend.app.config import _parse_trusted_proxies
        _parse_trusted_proxies.cache_clear()
        try:
            with self.assertLogs("blombooru", level=logging.WARNING) as cm:
                _parse_trusted_proxies("10.0.0.0/8,bad-entry-unique")
            warning_count = sum(1 for msg in cm.output if "bad-entry-unique" in msg)
            self.assertEqual(warning_count, 1)
            # Second call with the same raw string must not log again.
            with self.assertNoLogs("blombooru", level=logging.WARNING):
                _parse_trusted_proxies("10.0.0.0/8,bad-entry-unique")
        finally:
            _parse_trusted_proxies.cache_clear()

    def test_peer_ipv4_mapped_ipv6_normalised(self):
        """A direct peer of ::ffff:1.2.3.4 is returned as 1.2.3.4 (no proxy config)."""
        from backend.app.utils import request_helpers
        req = _make_request("::ffff:1.2.3.4")
        self.assertEqual(request_helpers.get_client_ip(req), "1.2.3.4")

class TestRateLimiterBypassClosed(unittest.TestCase):
    """Integration test: varying X-Forwarded-For must NOT evade the rate limiter."""

    def setUp(self):
        os.environ.pop("BLOMBOORU_TRUSTED_PROXIES", None)
        from backend.app.login_rate_limiter import LoginRateLimiter
        self.limiter = LoginRateLimiter(max_attempts=5, ban_duration_minutes=15)

    def _attempt(self, peer: str, xff=None):
        from fastapi import HTTPException
        req = _make_request(peer, xff=xff)
        try:
            self.limiter.check_rate_limit(req)
        except HTTPException as exc:
            return exc.status_code
        self.limiter.record_failed_attempt(req)
        return 401

    def test_xff_rotation_does_not_bypass_lockout(self):
        """Same TCP peer is locked out even if it rotates X-Forwarded-For values."""
        peer = "203.0.113.5"

        for i in range(5):
            status = self._attempt(peer, xff=f"10.10.10.{i}")
            self.assertEqual(status, 401)

        # Sixth attempt: the peer is now banned regardless of the XFF value.
        status = self._attempt(peer, xff="10.10.10.99")
        self.assertEqual(status, 429, "Rate limiter should have triggered HTTP 429")

    def test_different_peers_get_separate_buckets(self):
        """Two distinct TCP peers each have their own independent limit."""
        peer_a = "1.2.3.4"
        peer_b = "5.6.7.8"

        for _ in range(5):
            self._attempt(peer_a)

        self.assertEqual(self._attempt(peer_a), 429)
        self.assertEqual(self._attempt(peer_b), 401)

    def test_no_xff_direct_peer_is_banned(self):
        """Without any XFF header the direct peer is still correctly banned."""
        peer = "9.9.9.9"
        for _ in range(5):
            self._attempt(peer)
        self.assertEqual(self._attempt(peer), 429)

if __name__ == "__main__":
    unittest.main()
