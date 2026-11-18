from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from users.models import ParkingPermitGroups
from users.tests.factories.user import GroupFactory, UserFactory

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


@override_settings(LOCAL_ADMIN_ROLES_ENABLED=True)
class LocalAdminRoleAssignmentTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = UserFactory(is_staff=True)
        cls.editor.user_permissions.add(
            Permission.objects.get(
                codename="change_user", content_type__app_label="users"
            )
        )
        cls.target = UserFactory(is_staff=False, is_superuser=False)
        cls.role = GroupFactory(name=ParkingPermitGroups.INSPECTORS)

    def test_staff_user_cannot_submit_privilege_changes(self):
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse("admin:users_user_change", args=[self.target.pk]),
            {
                "username": self.target.username,
                "groups": [self.role.pk],
                "user_permissions": list(
                    self.editor.user_permissions.values_list("pk", flat=True)
                ),
                "is_staff": "on",
                "is_superuser": "on",
                "is_active": "on",
                "date_joined_0": self.target.date_joined.strftime("%Y-%m-%d"),
                "date_joined_1": self.target.date_joined.strftime("%H:%M:%S"),
                "_save": "Save",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
            response.context["adminform"].form.errors if response.context else None,
        )
        self.target.refresh_from_db()
        self.assertFalse(self.target.groups.exists())
        self.assertFalse(self.target.user_permissions.exists())
        self.assertFalse(self.target.is_staff)
        self.assertFalse(self.target.is_superuser)

    def test_superuser_can_assign_role(self):
        self.editor.is_superuser = True
        self.editor.save()
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse("admin:users_user_change", args=[self.target.pk]),
            {
                "username": self.target.username,
                "groups": [self.role.pk],
                "is_active": "on",
                "date_joined_0": self.target.date_joined.strftime("%Y-%m-%d"),
                "date_joined_1": self.target.date_joined.strftime("%H:%M:%S"),
                "_save": "Save",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
            response.context["adminform"].form.errors if response.context else None,
        )
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_inspectors)
        self.assertFalse(self.target.is_staff)
        self.assertFalse(self.target.is_superuser)

    @override_settings(LOCAL_ADMIN_ROLES_ENABLED=False)
    def test_flag_off_preserves_existing_admin_group_editing(self):
        self.client.force_login(self.editor)

        response = self.client.get(
            reverse("admin:users_user_change", args=[self.target.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="groups"')


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
