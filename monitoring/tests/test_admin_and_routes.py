import os
from pathlib import Path
from django.conf import settings
from django.test import SimpleTestCase, RequestFactory
from monitoring.api import status as api_status


class AdminAndRoutesTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_machine_admin_static_file_exists(self):
        """Verify the clipboard script exists in static directory."""
        static_dir = Path(settings.BASE_DIR) / "monitoring" / "static" / "admin" / "js"
        clipboard_file = static_dir / "machine_admin_clipboard.js"
        self.assertTrue(clipboard_file.exists(), f"Static script machine_admin_clipboard.js not found in {static_dir}")

    def test_change_list_template_includes_clipboard_script(self):
        """Verify Django admin change_list template loads the admin script."""
        template_path = Path(settings.BASE_DIR) / "monitoring" / "templates" / "admin" / "monitoring" / "machine" / "change_list.html"
        self.assertTrue(template_path.exists(), f"Template not found at {template_path}")

        content = template_path.read_text(encoding="utf-8")
        self.assertIn("machine_admin_clipboard.js", content, "change_list.html does not include machine_admin_clipboard.js")

    def test_ninja_api_status_endpoint(self):
        """Verify NinjaAPI /status returns 200 OK structure."""
        request = self.factory.get("/api/status")
        res = api_status(request)
        self.assertEqual(res["status"], "ok")
        self.assertIn("Plant Monitor", res["message"])
