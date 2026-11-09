from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


UA = {"HTTP_USER_AGENT": "Mozilla/5.0 (PlantMonitorTest)"}


class UrlAutoLoginTests(TestCase):
    def setUp(self):
        self.client.defaults.update(UA)
        self.password = "rahasia123"
        self.user = User.objects.create_user(username="operator01", password=self.password)

    def _url(self, username, password):
        encoded_user = quote(username, safe="")
        encoded_pass = quote(password, safe="")
        return f"/login/{encoded_user}/{encoded_pass}/"

    def test_session_cookie_age_is_48_hours(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 172800)

    def test_successful_login_redirects_to_dashboard(self):
        response = self.client.get(self._url("operator01", self.password))
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.assertAlmostEqual(
            self.client.session.get_expiry_age(),
            172800,
            delta=10,
        )

    def test_next_valid_internal_path(self):
        response = self.client.get(
            self._url("operator01", self.password) + "?next=/grafik"
        )
        self.assertRedirects(response, "/grafik", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_next_external_url_ignored(self):
        response = self.client.get(
            self._url("operator01", self.password) + "?next=https://example.com"
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_next_protocol_relative_ignored(self):
        response = self.client.get(
            self._url("operator01", self.password) + "?next=//evil.example"
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_next_login_path_ignored_to_avoid_loop(self):
        response = self.client.get(
            self._url("operator01", self.password) + "?next=/login/other/pass/"
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_wrong_password(self):
        response = self.client.get(self._url("operator01", "salah"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Password salah.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_username(self):
        response = self.client.get(self._url("tidakada", self.password))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username tidak ditemukan.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.get(self._url("operator01", self.password))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Akun dinonaktifkan. Hubungi admin.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_switch_user(self):
        other = User.objects.create_user(username="operator02", password="passdua")
        self.client.force_login(self.user)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

        response = self.client.get(self._url("operator02", "passdua"))
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), other.pk)

    def test_same_user_relogin_does_not_loop(self):
        self.client.force_login(self.user)
        response = self.client.get(self._url("operator01", self.password))
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_failed_login_does_not_logout_existing_session(self):
        self.client.force_login(self.user)
        response = self.client.get(self._url("operator01", "salah"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Password salah.")
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_special_character_password_with_encoding(self):
        special = "p@ss/w?rd#1"
        encoded_user = User.objects.create_user(username="op_enc", password=special)
        response = self.client.get(self._url("op_enc", special))
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), encoded_user.pk)

    def test_double_encode_password_fails(self):
        special = "p@ss"
        User.objects.create_user(username="op_dbl", password=special)
        double_pass = quote(quote(special, safe=""), safe="")
        response = self.client.get(f"/login/op_dbl/{double_pass}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Password salah.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_existing_login_page_still_works(self):
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Masuk")
        self.assertNotContains(response, "auto_login_error")

    def test_existing_login_form_post_still_works(self):
        response = self.client.post(
            reverse("login"),
            {"username": "operator01", "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_incomplete_path_is_404(self):
        response = self.client.get("/login/operator01/")
        self.assertEqual(response.status_code, 404)
