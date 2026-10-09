import html
import unittest
from urllib.parse import urlencode

from starlette.requests import Request

from backend.app.main import app, login_page
from backend.app.utils.url_security import get_safe_return_url, is_safe_return_url

class TestReturnUrlSecurity(unittest.IsolatedAsyncioTestCase):

    def test_is_safe_return_url_valid_paths(self):
        valid_paths = [
            "/",
            "/admin",
            "/admin/settings",
            "/media/123",
            "/album/45/media/67",
            "/search?q=tag:anime",
            "/search?tags=cat+dog&page=2",
            "/item:123",
            "/?tab=general",
            "/.//evil.com",
            "/%2Fevil.com",
            "/%5Cevil.com",
        ]
        for path in valid_paths:
            with self.subTest(path=path):
                self.assertTrue(is_safe_return_url(path), f"Expected {path} to be safe")
                self.assertEqual(get_safe_return_url(path), path)

    def test_is_safe_return_url_open_redirects_and_xss(self):
        unsafe_urls = [
            "https://evil.com",
            "http://evil.com",
            "http://evil.com/login",
            "//evil.com",
            "///evil.com",
            "/\\evil.com",
            "/\\\\evil.com",
            "javascript:alert(1)",
            "javascript:alert(document.cookie)",
            "JAVASCRIPT:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox(1)",
            "evil.com",
            "evil.com/path",
            "evil.com:8080/path",
            "foo:bar",
            "foo:bar?baz",
            "\\evil.com",
            "   /admin",
            "/\t/evil.com",
            "/\r\n/evil.com",
            "/\n/evil.com",
            "/admin\r\nSet-Cookie:malicious=1",
            "",
            None,
        ]
        for url in unsafe_urls:
            with self.subTest(url=url):
                self.assertFalse(is_safe_return_url(url), f"Expected {url} to be unsafe")
                self.assertEqual(get_safe_return_url(url), "/", f"Expected {url} to fall back to /")

    async def test_login_page_renders_safe_return_url(self):
        test_cases = [
            ("https://evil.com", "/"),
            ("https://evil.com?a=1&b=2#frag", "/"),
            ("//evil.com", "/"),
            ("/\\evil.com", "/"),
            ("javascript:alert(document.cookie)", "/"),
            ("javascript:alert(1)&foo=bar", "/"),
            ("data:text/html,alert(1)", "/"),
            ("/admin", "/admin"),
            ("/admin#settings", "/admin#settings"),
            ("/search?q=tag:test&sort=date", "/search?q=tag:test&sort=date"),
        ]
        for return_param, expected in test_cases:
            with self.subTest(return_param=return_param):
                scope = {
                    "type": "http",
                    "app": app,
                    "method": "GET",
                    "path": "/login",
                    "query_string": urlencode({"return": return_param}).encode("ascii"),
                    "headers": [(b"host", b"localhost")]
                }
                req = Request(scope)
                resp = await login_page(req)
                body = resp.body.decode()
                self.assertIn(f'value="{html.escape(expected)}"', body)
