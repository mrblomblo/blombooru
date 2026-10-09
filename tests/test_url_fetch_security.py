import unittest
from unittest.mock import MagicMock, patch

import requests

from backend.app.utils.url_fetch import (
    UrlFetchError,
    safe_request,
    fetch_media_stream,
    probe_media_url,
    validate_media_url,
)
from backend.app.utils.url_security import UrlValidationError

class TestUrlFetchSecurity(unittest.TestCase):

    def test_validate_media_url_rejects_ssrf(self):
        blocked_urls = [
            "http://127.0.0.1:8000/api/media",
            "http://localhost:8000/api/media",
            "http://169.254.169.254/latest/meta-data/",
            "http://100.64.0.1/internal",
            "http://100.100.100.200/latest/meta-data/",
            "http://10.0.0.1/admin",
            "http://192.168.1.1/secret",
            "http://172.16.0.1/",
            "http://[::1]/",
        ]
        for url in blocked_urls:
            with self.subTest(url=url):
                with self.assertRaises(UrlFetchError) as ctx:
                    validate_media_url(url)
                self.assertEqual(ctx.exception.status_code, 403)
                self.assertEqual(ctx.exception.message, "admin.media_management.url_import.error_ssrf_blocked")

    def test_validate_media_url_rejects_invalid_scheme(self):
        invalid_urls = [
            "ftp://example.com/image.png",
            "file:///etc/passwd",
            "gopher://example.com/",
            "javascript:alert(1)",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(UrlFetchError) as ctx:
                    validate_media_url(url)
                self.assertEqual(ctx.exception.status_code, 400)

    @patch("backend.app.utils.url_fetch._session.request")
    @patch("backend.app.utils.url_fetch.validate_url_not_ssrf")
    def test_probe_media_url_blocks_ssrf_redirect(self, mock_validate_ssrf, mock_request):
        # Initial URL is allowed by SSRF check
        # But redirect to 127.0.0.1 is blocked when SSRF check is executed on destination
        def ssrf_side_effect(url):
            if "127.0.0.1" in url or "localhost" in url:
                raise UrlValidationError("ssrf_blocked")

        mock_validate_ssrf.side_effect = ssrf_side_effect

        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 302
        mock_resp.headers = {"Location": "http://127.0.0.1:8000/admin"}
        mock_request.return_value = mock_resp

        with self.assertRaises(UrlFetchError) as ctx:
            probe_media_url("https://example.com/image.jpg")

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.message, "admin.media_management.url_import.error_ssrf_blocked")
        # Only the first request to example.com should have been made, none to 127.0.0.1
        self.assertEqual(mock_request.call_count, 1)
        self.assertEqual(mock_request.call_args[0][1], "https://example.com/image.jpg")
        self.assertFalse(mock_request.call_args[1]["allow_redirects"])

    @patch("backend.app.utils.url_fetch._session.request")
    @patch("backend.app.utils.url_fetch.validate_url_not_ssrf")
    def test_fetch_media_stream_blocks_ssrf_redirect(self, mock_validate_ssrf, mock_request):
        def ssrf_side_effect(url):
            if "169.254.169.254" in url:
                raise UrlValidationError("ssrf_blocked")

        mock_validate_ssrf.side_effect = ssrf_side_effect

        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 301
        mock_resp.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        mock_request.return_value = mock_resp

        with self.assertRaises(UrlFetchError) as ctx:
            fetch_media_stream("https://example.com/download")

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.message, "admin.media_management.url_import.error_ssrf_blocked")
        self.assertEqual(mock_request.call_count, 1)
        self.assertEqual(mock_request.call_args[0][1], "https://example.com/download")
        self.assertFalse(mock_request.call_args[1]["allow_redirects"])

    @patch("backend.app.utils.url_fetch._session.request")
    @patch("backend.app.utils.url_fetch.validate_url_not_ssrf")
    def test_follows_safe_redirects(self, mock_validate_ssrf, mock_request):
        mock_validate_ssrf.return_value = None

        resp_redirect = MagicMock(spec=requests.Response)
        resp_redirect.status_code = 302
        resp_redirect.headers = {"location": "https://cdn.example.com/real_image.png"}

        resp_final = MagicMock(spec=requests.Response)
        resp_final.status_code = 200
        resp_final.url = "https://cdn.example.com/real_image.png"
        resp_final.headers = {
            "content-type": "image/png",
            "content-length": "12345",
        }

        mock_request.side_effect = [resp_redirect, resp_final]

        result = probe_media_url("https://example.com/image.jpg")
        self.assertEqual(result["file_url"], "https://cdn.example.com/real_image.png")
        self.assertEqual(result["filename"], "real_image.png")
        self.assertEqual(result["content_type"], "image/png")
        self.assertEqual(result["file_size"], 12345)
        self.assertEqual(mock_request.call_count, 2)
        # Check both requests had allow_redirects=False
        for call in mock_request.call_args_list:
            self.assertFalse(call[1]["allow_redirects"])

    @patch("backend.app.utils.url_fetch._session.request")
    @patch("backend.app.utils.url_fetch.validate_url_not_ssrf")
    def test_relative_redirect(self, mock_validate_ssrf, mock_request):
        mock_validate_ssrf.return_value = None

        resp_redirect = MagicMock(spec=requests.Response)
        resp_redirect.status_code = 307
        resp_redirect.headers = {"location": "/static/images/picture.jpg"}

        resp_final = MagicMock(spec=requests.Response)
        resp_final.status_code = 200
        resp_final.url = "https://example.com/static/images/picture.jpg"
        resp_final.headers = {
            "content-type": "image/jpeg",
            "content-length": "54321",
        }

        mock_request.side_effect = [resp_redirect, resp_final]

        result = probe_media_url("https://example.com/get-image")
        self.assertEqual(result["file_url"], "https://example.com/static/images/picture.jpg")
        self.assertEqual(mock_request.call_count, 2)
        self.assertEqual(mock_request.call_args_list[1][0][1], "https://example.com/static/images/picture.jpg")

    @patch("backend.app.utils.url_fetch._session.request")
    @patch("backend.app.utils.url_fetch.validate_url_not_ssrf")
    def test_redirect_loop_limit(self, mock_validate_ssrf, mock_request):
        mock_validate_ssrf.return_value = None

        def create_redirect_resp(target):
            r = MagicMock(spec=requests.Response)
            r.status_code = 302
            r.headers = {"Location": target}
            return r

        mock_request.side_effect = [
            create_redirect_resp(f"https://example.com/loop/{i}") for i in range(15)
        ]

        with self.assertRaises(UrlFetchError) as ctx:
            safe_request("GET", "https://example.com/loop/0", timeout=(5, 5))

        self.assertIn("Too many redirects", ctx.exception.message)
        self.assertEqual(ctx.exception.status_code, 400)

    @patch("backend.app.utils.url_fetch._session.request")
    @patch("backend.app.utils.url_fetch.validate_url_not_ssrf")
    def test_303_redirect_preserves_head_method(self, mock_validate_ssrf, mock_request):
        mock_validate_ssrf.return_value = None

        resp_redirect = MagicMock(spec=requests.Response)
        resp_redirect.status_code = 303
        resp_redirect.headers = {"location": "https://cdn.example.com/target.jpg"}

        resp_final = MagicMock(spec=requests.Response)
        resp_final.status_code = 200
        resp_final.url = "https://cdn.example.com/target.jpg"
        resp_final.headers = {
            "content-type": "image/jpeg",
            "content-length": "1024",
        }

        mock_request.side_effect = [resp_redirect, resp_final]

        safe_request("HEAD", "https://example.com/start", timeout=(5, 5))

        self.assertEqual(mock_request.call_count, 2)
        # Verify second hop remained HEAD
        self.assertEqual(mock_request.call_args_list[0][0][0], "HEAD")
        self.assertEqual(mock_request.call_args_list[1][0][0], "HEAD")

    @patch("backend.app.utils.url_fetch.validate_url_not_ssrf")
    def test_safe_request_uses_custom_session_and_user_agent(self, mock_validate_ssrf):
        mock_validate_ssrf.return_value = None

        mock_session = MagicMock(spec=requests.Session)
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_session.request.return_value = mock_resp

        resp = safe_request(
            "GET",
            "https://example.com/test",
            timeout=(5, 5),
            session=mock_session,
            user_agent="CustomAgent/1.0",
            headers={"X-Test": "123"},
        )

        self.assertEqual(resp, mock_resp)
        self.assertTrue(mock_session.request.called)
        called_headers = mock_session.request.call_args[1]["headers"]
        self.assertEqual(called_headers.get("User-Agent"), "CustomAgent/1.0")
        self.assertEqual(called_headers.get("X-Test"), "123")

if __name__ == "__main__":
    unittest.main()
