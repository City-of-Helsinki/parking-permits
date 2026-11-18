from itertools import product

from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Group, Permission
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from users.models import ParkingPermitGroups
from users.tests.factories.user import GroupFactory, UserFactory

TEST_PASSWORD = "test-admin-password"


class GroupAdminSecurityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = UserFactory(is_active=True, is_staff=True, is_superuser=False)
        cls.editor.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="auth", content_type__model="group"
            )
        )
        cls.superuser = UserFactory(is_active=True, is_staff=True, is_superuser=True)
        cls.group = GroupFactory(name="admin-security-test")

    def test_staff_cannot_mutate_groups_despite_group_permissions(self):
        self.client.force_login(self.editor)
        requests = (
            (reverse("admin:auth_group_add"), {"name": "unauthorized-group"}, 403),
            (
                reverse("admin:auth_group_change", args=[self.group.pk]),
                {"name": "unauthorized-rename"},
                403,
            ),
            (
                reverse("admin:auth_group_delete", args=[self.group.pk]),
                {"post": "yes"},
                403,
            ),
            (
                reverse("admin:auth_group_changelist"),
                {
                    "action": "delete_selected",
                    "_selected_action": [self.group.pk],
                    "post": "yes",
                },
                200,
            ),
        )
        for enabled, (url, data, expected_status) in product((False, True), requests):
            with (
                self.subTest(enabled=enabled, url=url),
                override_settings(LOCAL_ADMIN_ROLES_ENABLED=enabled),
            ):
                response = self.client.post(url, data)
                self.assertEqual(response.status_code, expected_status)
                self.group.refresh_from_db()
                self.assertEqual(self.group.name, "admin-security-test")
                self.assertFalse(
                    Group.objects.filter(name="unauthorized-group").exists()
                )

    def test_staff_can_still_view_groups(self):
        self.client.force_login(self.editor)
        urls = (
            reverse("admin:auth_group_changelist"),
            reverse("admin:auth_group_change", args=[self.group.pk]),
        )
        for enabled, url in product((False, True), urls):
            with (
                self.subTest(enabled=enabled, url=url),
                override_settings(LOCAL_ADMIN_ROLES_ENABLED=enabled),
            ):
                response = self.client.get(url)
                self.assertNotContains(response, 'name="name"', status_code=200)

    def test_superuser_can_add_change_and_delete_groups(self):
        self.client.force_login(self.superuser)
        for enabled in (False, True):
            with (
                self.subTest(enabled=enabled),
                override_settings(LOCAL_ADMIN_ROLES_ENABLED=enabled),
            ):
                response = self.client.post(
                    reverse("admin:auth_group_add"), {"name": "authorized-group"}
                )
                self.assertEqual(response.status_code, 302)
                group = Group.objects.get(name="authorized-group")

                response = self.client.post(
                    reverse("admin:auth_group_change", args=[group.pk]),
                    {"name": "authorized-rename"},
                )
                self.assertEqual(response.status_code, 302)
                group.refresh_from_db()
                self.assertEqual(group.name, "authorized-rename")

                response = self.client.post(
                    reverse("admin:auth_group_delete", args=[group.pk]), {"post": "yes"}
                )
                self.assertEqual(response.status_code, 302)
                self.assertFalse(Group.objects.filter(pk=group.pk).exists())


class UserAdminPasswordSecurityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = UserFactory(is_active=True, is_staff=True, is_superuser=False)
        cls.editor.user_permissions.add(
            Permission.objects.get(
                codename="change_user", content_type__app_label="users"
            )
        )
        cls.superuser = UserFactory(is_active=True, is_staff=True, is_superuser=True)
        cls.target = UserFactory(is_active=True, is_staff=False, is_superuser=False)
        cls.superuser.set_password(TEST_PASSWORD)
        cls.superuser.save()

    def test_staff_cannot_view_or_change_superuser_password(self):
        self.client.force_login(self.editor)
        url = reverse("admin:auth_user_password_change", args=[self.superuser.pk])
        original_password = self.superuser.password
        for enabled, method in product((False, True), ("get", "post")):
            with (
                self.subTest(enabled=enabled, method=method),
                override_settings(LOCAL_ADMIN_ROLES_ENABLED=enabled),
            ):
                response = getattr(self.client, method)(
                    url,
                    {
                        "password1": "unauthorized-password",
                        "password2": "unauthorized-password",
                    }
                    if method == "post"
                    else {},
                )
                self.assertEqual(response.status_code, 403)
                self.superuser.refresh_from_db()
                self.assertEqual(self.superuser.password, original_password)

    def test_permitted_password_changes_still_work(self):
        accounts = (
            (self.editor, self.target),
            (self.editor, self.editor),
            (self.superuser, self.target),
            (self.superuser, self.superuser),
        )
        for enabled, (editor, target) in product((False, True), accounts):
            with (
                self.subTest(enabled=enabled, editor=editor.pk, target=target.pk),
                override_settings(LOCAL_ADMIN_ROLES_ENABLED=enabled),
            ):
                self.client.force_login(editor)
                url = reverse("admin:auth_user_password_change", args=[target.pk])
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                password = f"changed-admin-password-{enabled}-{editor.pk}-{target.pk}"
                response = self.client.post(
                    url,
                    {
                        "password1": password,
                        "password2": password,
                        "usable_password": "true",
                    },
                )
                self.assertEqual(response.status_code, 302)
                target.refresh_from_db()
                self.assertTrue(target.check_password(password))

    def test_missing_account_keeps_django_not_found_response(self):
        target_pk = self.target.pk
        self.target.delete()
        url = reverse("admin:auth_user_password_change", args=[target_pk])
        for enabled, editor in product((False, True), (self.editor, self.superuser)):
            with (
                self.subTest(enabled=enabled, editor=editor.pk),
                override_settings(LOCAL_ADMIN_ROLES_ENABLED=enabled),
            ):
                self.client.force_login(editor)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)


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
