from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, RequestFactory
from django.http import HttpResponse
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from monitoring.middleware import BotBlockerMiddleware
from monitoring.decorators import (
    user_can_access_page,
    position_required,
    get_user_allowed_pages,
)
from monitoring.utils.manual_status import (
    format_status_since_display,
    get_status_since_info,
    MANUAL_STATUS_RUNNING,
    MANUAL_STATUS_STOP,
)


class SecurityAndRbacTest(SimpleTestCase):
    """
    Unit tests for BotBlocker WAF middleware (security rules, scanner detection,
    exploit path prevention, X-Forwarded-For IP extraction) and Role-Based Access Control (RBAC).
    """

    def setUp(self):
        self.rf = RequestFactory()
        # Mock get_response handler
        self.mock_get_response = MagicMock(return_value=HttpResponse("OK", status=200))
        self.middleware = BotBlockerMiddleware(self.mock_get_response)

    def test_bot_blocker_rejects_empty_user_agent(self):
        """Requests without HTTP_USER_AGENT must be rejected immediately with 400."""
        req = self.rf.get("/api/v1/status")
        if "HTTP_USER_AGENT" in req.META:
            del req.META["HTTP_USER_AGENT"]

        resp = self.middleware(req)
        self.assertEqual(resp.status_code, 400)
        self.mock_get_response.assert_not_called()

    def test_bot_blocker_rejects_malicious_scanner_user_agents(self):
        """Requests with scanner / automated tool User-Agents must be rejected with 403."""
        malicious_uas = [
            "sqlmap/1.6#stable",
            "Nikto/2.1.6",
            "Nmap Scripting Engine",
            "masscan/1.0",
            "python-requests/2.31.0",
            "Go-http-client/1.1",
            "curl/7.88.1",
            "Wget/1.21.3",
        ]
        for ua in malicious_uas:
            req = self.rf.get("/api/v1/status", HTTP_USER_AGENT=ua)
            resp = self.middleware(req)
            self.assertEqual(
                resp.status_code,
                403,
                f"Scanner UA '{ua}' should be blocked with 403 Forbidden",
            )

    def test_bot_blocker_rejects_exploit_paths(self):
        """Requests targeting common CMS / exploit probe paths must be blocked with 404."""
        exploit_paths = [
            "/.env",
            "/.git/config",
            "/wp-admin/install.php",
            "/phpmyadmin/index.php",
            "/shell.php",
            "/admin.php",
            "/actuator/health",
        ]
        browser_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0"
        for path in exploit_paths:
            req = self.rf.get(path, HTTP_USER_AGENT=browser_ua)
            resp = self.middleware(req)
            self.assertEqual(
                resp.status_code,
                404,
                f"Exploit probe path '{path}' should be blocked with 404",
            )

    def test_bot_blocker_allows_legitimate_browser_and_extracts_xff(self):
        """Legitimate browser requests to normal application paths must pass through (200 OK)."""
        browser_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
        req = self.rf.get(
            "/api/v1/status",
            HTTP_USER_AGENT=browser_ua,
            HTTP_X_FORWARDED_FOR="192.168.1.100, 10.0.0.1",
        )

        with patch.object(self.middleware, "_is_blocked_in_db", return_value=False), \
             patch.object(self.middleware, "_upsert_ip"):

            resp = self.middleware(req)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(self.middleware._get_ip(req), "192.168.1.100")

    def test_bot_blocker_blacklisted_ip(self):
        """Requests from blacklisted IPs must be blocked with 403."""
        browser_ua = "Mozilla/5.0"
        req = self.rf.get("/", HTTP_USER_AGENT=browser_ua, REMOTE_ADDR="198.51.100.1")

        with patch.object(self.middleware, "_is_blocked_in_db", return_value=True), \
             patch.object(self.middleware, "_upsert_ip"):

            resp = self.middleware(req)
            self.assertEqual(resp.status_code, 403)
            self.assertIn("Akses dari alamat IP Anda telah diblokir", resp.content.decode("utf-8"))

    def test_rbac_superuser_and_staff_bypass(self):
        """Superusers and staff members have unrestricted access to any page."""
        admin_user = MagicMock(is_superuser=True, is_staff=True)
        staff_user = MagicMock(is_superuser=False, is_staff=True)

        self.assertTrue(user_can_access_page(admin_user, "secret_page"))
        self.assertTrue(user_can_access_page(staff_user, "engineer_workspace"))
        self.assertTrue(user_can_access_page(admin_user, "analytics"))

    def test_rbac_operator_permission_checks(self):
        """Regular operators only have access if their assigned position has active page permissions."""
        operator = MagicMock(is_superuser=False, is_staff=False)

        # Subcase 1: No operator profile
        operator.operatorprofile = None
        self.assertFalse(user_can_access_page(operator, "dashboard"))

        # Subcase 2: Has operator profile but no position
        mock_profile = MagicMock(position=None)
        operator.operatorprofile = mock_profile
        self.assertFalse(user_can_access_page(operator, "dashboard"))

        # Subcase 3: Has position with 'dashboard' allowed, but not 'engineer'
        def filter_mock(code, is_active):
            m = MagicMock()
            m.exists.return_value = (code == "dashboard")
            return m

        mock_position = MagicMock()
        mock_position.allowed_pages.filter = filter_mock
        mock_profile.position = mock_position

        self.assertTrue(user_can_access_page(operator, "dashboard"))
        self.assertFalse(user_can_access_page(operator, "engineer"))

    def test_position_required_view_decorator_denial(self):
        """Verify position_required view decorator renders access_denied.html (403) on denial."""
        operator = MagicMock(is_superuser=False, is_staff=False)
        mock_profile = MagicMock(position=None)
        operator.operatorprofile = mock_profile

        @position_required("restricted_page")
        def protected_view(request):
            return HttpResponse("Protected Content")

        req = self.rf.get("/restricted")
        req.user = operator

        with patch("monitoring.decorators.render") as mock_render:
            mock_render.return_value = HttpResponse("Access Denied", status=403)
            resp = protected_view(req)
            self.assertEqual(resp.status_code, 403)
            mock_render.assert_called_once()

    def test_format_status_since_display(self):
        """Verify relative status time formatting in Bahasa Indonesia."""
        now = timezone.localtime()
        self.assertIsNone(format_status_since_display(None))

        # Today at specific time (in local timezone)
        today_dt = now.replace(hour=14, minute=30, second=0)
        display_today = format_status_since_display(today_dt)
        self.assertIn("14:30", display_today)
        self.assertTrue(display_today.startswith("Hari ini"))

        # Yesterday (in local timezone)
        yesterday_dt = (now - timedelta(days=1)).replace(hour=9, minute=15, second=0)
        display_yesterday = format_status_since_display(yesterday_dt)
        self.assertIn("09:15", display_yesterday)
        self.assertTrue(display_yesterday.startswith("Kemarin"))

    def test_get_status_since_info_manual_mode(self):
        """Verify get_status_since_info for manual machine running vs stop."""
        mock_m = MagicMock()
        mock_m.operation_mode = "MANUAL"
        mock_m.manual_status = "Running"
        mock_m.status_changed_at = timezone.now() - timedelta(minutes=45)

        with patch("monitoring.utils.manual_status._get_manual_status_timestamp", return_value=mock_m.status_changed_at):
            info = get_status_since_info(mock_m)
            self.assertTrue(info["is_active"])
            self.assertGreaterEqual(info["duration_minutes"], 44)
            self.assertLessEqual(info["duration_minutes"], 46)

            # Inactive stop machine
            mock_m.manual_status = "Stop"
            info_stop = get_status_since_info(mock_m)
            self.assertFalse(info_stop["is_active"])
