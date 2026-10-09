import asyncio
import unittest
from unittest.mock import MagicMock, patch

from backend.app.models import BooruConfig
from backend.app.routes.booru_import import proxy_image
from backend.app.services.booru import (DanbooruClient, clear_client_cache,
                                       get_booru_config_for_url,
                                       get_client_for_url,
                                       get_user_agent_for_url)
from tests.test_base import BlombooruTestSandboxMixin

class TestDanbooruAccountId(unittest.TestCase, BlombooruTestSandboxMixin):
    def setUp(self):
        self.setup_sandbox()
        clear_client_cache()

    def tearDown(self):
        clear_client_cache()
        self.teardown_sandbox()

    def test_danbooru_client_without_credentials(self):
        client = DanbooruClient("https://danbooru.donmai.us")
        self.assertIsNone(client.user_id)
        self.assertEqual(client.session.headers.get("User-Agent"), "Blombooru/1.0 (booru-import)")

    @patch("requests.Session.get")
    def test_danbooru_client_fetches_numeric_account_id(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 1633079,
            "name": "test_user",
            "level": 10,
        }
        mock_get.return_value = mock_resp

        client = DanbooruClient(
            "https://danbooru.donmai.us",
            api_key="secret123",
            username="test_user",
        )

        self.assertEqual(client.ensure_user_id(), 1633079)
        self.assertEqual(client.user_id, 1633079)
        self.assertEqual(
            client.session.headers.get("User-Agent"),
            "Blombooru/1.0 (booru-import); user #1633079",
        )
        # Verify it did not use username in user #<id>
        self.assertNotIn("test_user", client.session.headers.get("User-Agent"))

    @patch("requests.Session.get")
    def test_danbooru_client_handles_profile_failure_gracefully(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        client = DanbooruClient(
            "https://danbooru.donmai.us",
            api_key="invalid_key",
            username="test_user",
        )

        self.assertIsNone(client.ensure_user_id())
        self.assertIsNone(client.user_id)
        self.assertEqual(client.session.headers.get("User-Agent"), "Blombooru/1.0 (booru-import)")

    def test_get_booru_config_exact_domain_matching_only(self):
        config = BooruConfig(
            domain="safebooru.donmai.us",
            username="safebooru_user",
            api_key="safebooru_key",
        )
        self.db.add(config)
        self.db.commit()

        # Exact match succeeds
        matched = get_booru_config_for_url(self.db, "https://safebooru.donmai.us/posts/100")
        self.assertIsNotNone(matched)
        self.assertEqual(matched.domain, "safebooru.donmai.us")

        # Different subdomain must NOT match (no credential leakage)
        unmatched = get_booru_config_for_url(self.db, "https://danbooru.donmai.us/posts/100")
        self.assertIsNone(unmatched)

        unmatched_beta = get_booru_config_for_url(self.db, "https://betabooru.donmai.us/posts/100")
        self.assertIsNone(unmatched_beta)

    def test_factory_requires_both_username_and_api_key(self):
        # Only username, no api_key
        config_no_key = BooruConfig(
            domain="danbooru.donmai.us",
            username="lonely_user",
            api_key=None,
        )
        self.db.add(config_no_key)
        self.db.commit()

        client = get_client_for_url("https://danbooru.donmai.us/posts/1", db=self.db)
        self.assertIsNotNone(client)
        self.assertIsNone(client.api_key)
        self.assertIsNone(client.username)
        self.assertEqual(client.session.headers.get("User-Agent"), "Blombooru/1.0 (booru-import)")

    @patch("requests.Session.get")
    def test_get_user_agent_for_url_uses_client_account_id(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1633079, "name": "dan_user"}
        mock_get.return_value = mock_resp

        config = BooruConfig(
            domain="danbooru.donmai.us",
            username="dan_user",
            api_key="dan_key",
        )
        self.db.add(config)
        self.db.commit()

        ua = get_user_agent_for_url("https://danbooru.donmai.us/data/sample.jpg", db=self.db)
        self.assertEqual(ua, "Blombooru/1.0 (booru-import); user #1633079")

        # Different subdomain returns default UA
        diff_ua = get_user_agent_for_url("https://safebooru.donmai.us/data/sample.jpg", db=self.db)
        self.assertEqual(diff_ua, "Blombooru/1.0 (booru-import)")

    @patch("backend.app.routes.booru_import.safe_request")
    @patch("backend.app.routes.booru_import.validate_url_not_ssrf")
    @patch("requests.Session.get")
    def test_proxy_image_uses_shared_helper(self, mock_session_get, mock_ssrf, mock_safe_request):
        mock_profile_resp = MagicMock()
        mock_profile_resp.status_code = 200
        mock_profile_resp.json.return_value = {"id": 1633079, "name": "dan_user"}
        mock_session_get.return_value = mock_profile_resp

        config = BooruConfig(
            domain="danbooru.donmai.us",
            username="dan_user",
            api_key="dan_key",
        )
        self.db.add(config)
        self.db.commit()

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.headers = {"content-type": "image/jpeg"}
        fake_resp.iter_content.return_value = [b"data"]
        mock_safe_request.return_value = fake_resp

        asyncio.run(proxy_image("https://danbooru.donmai.us/sample.jpg", current_user=None, db=self.db))

        self.assertTrue(mock_safe_request.called)
        self.assertEqual(mock_safe_request.call_args[1].get("user_agent"), "Blombooru/1.0 (booru-import); user #1633079")

    def test_danbooru_client_init_does_not_make_network_call(self):
        with patch("requests.Session.get") as mock_get:
            client = DanbooruClient(
                "https://danbooru.donmai.us",
                api_key="secret123",
                username="test_user",
            )
            # Init must NOT make any blocking network calls
            self.assertFalse(mock_get.called)
            self.assertIsNone(client.user_id)

            # Lazy evaluation happens upon ensure_user_id()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"id": 1633079, "name": "test_user"}
            mock_get.return_value = mock_resp

            client.ensure_user_id()
            self.assertTrue(mock_get.called)
            self.assertEqual(client.user_id, 1633079)
            self.assertEqual(client.session.headers.get("User-Agent"), "Blombooru/1.0 (booru-import); user #1633079")

    @patch("requests.Session.get")
    def test_transient_failure_allows_retry_after_interval(self, mock_get):
        mock_fail = MagicMock()
        mock_fail.status_code = 500
        mock_get.return_value = mock_fail

        client = DanbooruClient(
            "https://danbooru.donmai.us",
            api_key="secret123",
            username="test_user",
        )
        self.assertIsNone(client.ensure_user_id())
        self.assertFalse(client._permanent_auth_failure)
        self.assertEqual(mock_get.call_count, 1)

        # Immediate next call within interval does not hammer the server
        self.assertIsNone(client.ensure_user_id())
        self.assertEqual(mock_get.call_count, 1)

        # After interval elapsed, transient error is retried
        client._last_profile_attempt -= 61.0
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {"id": 1633079, "name": "test_user"}
        mock_get.return_value = mock_ok

        self.assertEqual(client.ensure_user_id(), 1633079)
        self.assertEqual(client.session.headers.get("User-Agent"), "Blombooru/1.0 (booru-import); user #1633079")

    @patch("requests.Session.get")
    def test_permanent_auth_failure_stops_retry(self, mock_get):
        mock_401 = MagicMock()
        mock_401.status_code = 401
        mock_get.return_value = mock_401

        client = DanbooruClient(
            "https://danbooru.donmai.us",
            api_key="wrong_key",
            username="test_user",
        )
        self.assertIsNone(client.ensure_user_id())
        self.assertTrue(client._permanent_auth_failure)
        self.assertEqual(mock_get.call_count, 1)

        # Even after interval, 401/403 credentials error is not retried
        client._last_profile_attempt -= 61.0
        self.assertIsNone(client.ensure_user_id())
        self.assertEqual(mock_get.call_count, 1)

    def test_case_insensitive_domain_matching(self):
        config = BooruConfig(
            domain="Danbooru.Donmai.Us",
            username="mixed_user",
            api_key="key",
        )
        self.db.add(config)
        self.db.commit()

        matched = get_booru_config_for_url(self.db, "https://danbooru.donmai.us/posts/100")
        self.assertIsNotNone(matched)
        self.assertEqual(matched.username, "mixed_user")

    def test_ipv6_and_port_handling(self):
        config = BooruConfig(
            domain="[::1]:8080",
            username="local_user",
            api_key="key",
        )
        self.db.add(config)
        self.db.commit()

        matched = get_booru_config_for_url(self.db, "http://[::1]:8080/data/test.jpg")
        self.assertIsNotNone(matched)
        self.assertEqual(matched.username, "local_user")

    @patch("requests.Session.get")
    def test_scheme_preserved_for_http_booru(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 999, "name": "local_user"}
        mock_get.return_value = mock_resp

        config = BooruConfig(
            domain="danbooru.local",
            username="local_user",
            api_key="local_key",
        )
        self.db.add(config)
        self.db.commit()

        ua = get_user_agent_for_url("http://danbooru.local/data/test.jpg", db=self.db)
        self.assertEqual(ua, "Blombooru/1.0 (booru-import); user #999")
        # Verify the client URL used http:// and not https://
        self.assertTrue(mock_get.called)
        called_url = mock_get.call_args[0][0]
        self.assertTrue(called_url.startswith("http://danbooru.local"))

    @patch("requests.Session.get")
    def test_direct_url_handled_without_synthetic_fallback(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1234, "name": "direct_user"}
        mock_get.return_value = mock_resp

        config = BooruConfig(
            domain="danbooru.donmai.us",
            username="direct_user",
            api_key="direct_key",
        )
        self.db.add(config)
        self.db.commit()

        # Direct post URL is handled directly by get_client_for_url
        ua = get_user_agent_for_url("https://danbooru.donmai.us/posts/555", db=self.db)
        self.assertEqual(ua, "Blombooru/1.0 (booru-import); user #1234")

    @patch("requests.Session.get")
    def test_get_user_agent_single_db_query_efficiency(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1633079, "name": "dan_user"}
        mock_get.return_value = mock_resp

        config = BooruConfig(
            domain="danbooru.donmai.us",
            username="dan_user",
            api_key="dan_key",
        )
        self.db.add(config)
        self.db.commit()

        with patch.object(self.db, "query", wraps=self.db.query) as spy_query:
            ua = get_user_agent_for_url("https://danbooru.donmai.us/data/sample.jpg", db=self.db)
            self.assertEqual(ua, "Blombooru/1.0 (booru-import); user #1633079")
            # Must only execute at most 1 DB query, not 2
            self.assertEqual(spy_query.call_count, 1)

if __name__ == "__main__":
    unittest.main()
