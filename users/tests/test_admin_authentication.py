from django.contrib.auth import SESSION_KEY
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from users.tests.factories.user import UserFactory

TEST_PASSWORD = "test-admin-password"


@override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
class AdminAuthenticationTest(SimpleTestCase):
    def test_admin_login_offers_central_helsinki_login(self):
        response = self.client.get(reverse("admin:login"))

        self.assertContains(response, reverse("helusers:auth_login"))

    def test_central_login_redirects_to_oidc_preserving_next(self):
        next_url = reverse("admin:index")

        response = self.client.post(reverse("helusers:auth_login"), {"next": next_url})

        self.assertRedirects(
            response,
            reverse(
                "social:begin",
                kwargs={"backend": "tunnistamo"},
                query={"next": next_url},
            ),
            status_code=307,
            fetch_redirect_response=False,
        )


class AdminAuthenticationSessionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory(is_active=True, is_staff=True)
        cls.user.set_password(TEST_PASSWORD)
        cls.user.save()

    @override_settings(HELUSERS_PASSWORD_LOGIN_ALLOWLIST=[])
    def test_password_login_respects_setting(self):
        for disabled in (False, True):
            with (
                self.subTest(disabled=disabled),
                override_settings(HELUSERS_PASSWORD_LOGIN_DISABLED=disabled),
            ):
                self.client.logout()
                logged_in = self.client.login(
                    username=self.user.username, password=TEST_PASSWORD
                )

                self.assertEqual(logged_in, not disabled)

    def test_active_staff_user_can_access_admin(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)

    def test_non_staff_user_cannot_access_admin(self):
        self.user.is_staff = False
        self.user.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("admin:index"))

        self.assertRedirects(
            response,
            reverse("admin:login", query={"next": reverse("admin:index")}),
        )

    def test_logout_clears_authenticated_session(self):
        self.client.force_login(self.user)
        self.assertIn(SESSION_KEY, self.client.session)

        response = self.client.post(reverse("helusers:auth_logout"))

        self.assertRedirects(
            response, reverse("admin:index"), fetch_redirect_response=False
        )
        self.assertNotIn(SESSION_KEY, self.client.session)
