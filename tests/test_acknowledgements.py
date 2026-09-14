import unittest
import asyncio
from pathlib import Path
from backend.app.routes.acknowledgements import get_acknowledgements, _render_acknowledgements
from scripts.generate_acknowledgements import (
    find_requirements_packages,
    load_vendored_dependencies,
)

class TestAcknowledgements(unittest.TestCase):
    def test_acknowledgements_file_exists(self):
        ack_path = Path("ACKNOWLEDGEMENTS.md")
        self.assertTrue(ack_path.exists())
        self.assertTrue(ack_path.is_file())
        content = ack_path.read_text(encoding="utf-8")
        self.assertIn("https://github.com/mrblomblo/blombooru/blob/main/LICENSE.txt", content)
        self.assertIn("Chart.js", content)
        self.assertIn("Name: fastapi", content)
        self.assertIn("Name: tailwindcss", content)
        self.assertIn("Name: chart.js", content)

    def test_license_files_exist(self):
        tailwind_lic = Path("tailwind/Tailwind.LICENSE.txt")
        chart_lic = Path("frontend/static/js/vendor/chart.js.LICENSE.txt")
        self.assertTrue(tailwind_lic.exists())
        self.assertTrue(chart_lic.exists())

    def test_package_count(self):
        pkgs = find_requirements_packages()
        self.assertGreater(len(pkgs), 50)
        vendored = load_vendored_dependencies()
        total_dependencies = len(pkgs) + len(vendored)
        self.assertEqual(total_dependencies, 69)

    def test_backend_route_render(self):
        html = _render_acknowledgements()
        self.assertIsNotNone(html)
        self.assertIn("acknowledgement-preamble", html)
        self.assertIn("acknowledgement-card", html)
        self.assertIn("fastapi", html)
        self.assertIn("tailwindcss", html)
        self.assertIn("chart.js", html)

    def test_api_async_endpoint(self):
        res = asyncio.run(get_acknowledgements())
        self.assertIsNotNone(res.html)
        self.assertIn("acknowledgement-card", res.html)

if __name__ == "__main__":
    unittest.main()
