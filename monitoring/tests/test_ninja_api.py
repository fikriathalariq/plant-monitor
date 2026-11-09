import json
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase
from ninja.testing import TestClient

from monitoring.api import api


class DjangoNinjaApiContractTest(SimpleTestCase):
    """
    Unit test suite for Django Ninja REST API:
    - OpenAPI/Swagger schema generation and route collision checks across all 18 routers
    - Health check endpoint under normal and failure conditions
    - Parameter validation and Pydantic schema enforcement (422)
    - Authentication endpoints (/auth/login, /auth/logout, /auth/me)
    """

    def setUp(self):
        self.client = TestClient(api)

    def test_openapi_schema_generation_and_all_18_routers(self):
        """
        Verify that OpenAPI schema can be generated cleanly across all registered routers.
        This catches any Pydantic schema conflicts, invalid type annotations, or route name collisions.
        """
        schema = api.get_openapi_schema()
        self.assertIsInstance(schema, dict)
        self.assertIn("openapi", schema)
        self.assertIn("paths", schema)

        paths = schema["paths"]
        # Verify core operational routes exist in OpenAPI specification
        self.assertIn("/api/v1/status", paths)
        self.assertIn("/api/v1/health", paths)
        self.assertIn("/api/v1/auth/login", paths)
        self.assertIn("/api/v1/auth/me", paths)

        # Verify that all major router prefixes are mounted
        router_prefixes = [
            "/api/v1/auth/",
            "/api/v1/dashboard/",
            "/api/v1/report/",
            "/api/v1/anomalies/",
            "/api/v1/machines/",
            "/api/v1/analytics/",
            "/api/v1/engineer/",
            "/api/v1/planning/",
        ]
        for prefix in router_prefixes:
            has_prefix = any(p.startswith(prefix.rstrip("/")) for p in paths)
            self.assertTrue(has_prefix, f"Prefix '{prefix}' must have active endpoints in OpenAPI schema")

    def test_status_endpoint(self):
        """Verify GET /api/v1/status returns 200 OK and expected greeting."""
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("Plant Monitor", data["message"])

    def test_health_endpoint_healthy(self):
        """Verify GET /api/v1/health returns healthy payload when DB cursor succeeds."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("monitoring.api.connection", mock_conn):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "healthy")
            self.assertEqual(data["database"], "connected")
            self.assertIn("slot", data)
            self.assertIn("port", data)
            self.assertIn("timestamp", data)

    def test_health_endpoint_database_failure_503(self):
        """Verify GET /api/v1/health returns 503 Service Unavailable when DB is down."""
        mock_conn = MagicMock()
        mock_conn.cursor.side_effect = Exception("Connection refused by PostgreSQL")

        with patch("monitoring.api.connection", mock_conn):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 503)
            self.assertIn("Database health check failed", response.json().get("detail", ""))

    def test_health_cache_flush_local_vs_remote(self):
        """Verify that ?flush_cache=1 is only executed for localhost and ignored for remote IPs."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("monitoring.api.connection", mock_conn), \
             patch("monitoring.api.cache.clear") as mock_cache_clear:

            # Localhost call (127.0.0.1) -> cache flushed
            resp_local = self.client.get("/health?flush_cache=1", META={"REMOTE_ADDR": "127.0.0.1"})
            self.assertEqual(resp_local.status_code, 200)
            self.assertTrue(resp_local.json()["cache_flushed"])
            mock_cache_clear.assert_called_once()

            mock_cache_clear.reset_mock()

            # Remote IP call (192.168.1.50) -> cache flush ignored
            resp_remote = self.client.get("/health?flush_cache=1", META={"REMOTE_ADDR": "192.168.1.50"})
            self.assertEqual(resp_remote.status_code, 200)
            self.assertFalse(resp_remote.json()["cache_flushed"])
            mock_cache_clear.assert_not_called()

    def test_auth_me_unauthenticated(self):
        """Verify GET /api/v1/auth/me returns authenticated=False for anonymous requests."""
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["authenticated"])

    def test_auth_login_invalid_credentials_401(self):
        """Verify POST /api/v1/auth/login returns 401 when authenticate fails."""
        with patch("monitoring.api_auth.authenticate", return_value=None):
            payload = {"username": "wrong_user", "password": "wrong_password"}
            response = self.client.post("/auth/login", json=payload)
            self.assertEqual(response.status_code, 401)
            data = response.json()
            self.assertFalse(data["success"])
            self.assertIn("Username atau password salah", data["message"])

    def test_auth_login_pydantic_validation_error_422(self):
        """Verify POST /api/v1/auth/login returns 422 Unprocessable Entity when fields are missing."""
        # Empty payload missing username & password
        response = self.client.post("/auth/login", json={})
        self.assertEqual(response.status_code, 422)

    def test_auth_logout(self):
        """Verify POST /api/v1/auth/logout returns success."""
        with patch("monitoring.api_auth.logout"):
            response = self.client.post("/auth/logout")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["success"])
