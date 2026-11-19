from types import SimpleNamespace

from django.test import TestCase, override_settings
from helusers.models import ADGroupMapping
from helusers.pipeline import create_or_update_user
from helusers.user_utils import get_or_create_user

from users.models import ParkingPermitGroups
from users.tests.factories.user import ADGroupFactory, GroupFactory, UserFactory


@override_settings(LOCAL_ADMIN_ROLES_ENABLED=True)
class LocalAdminRoleSyncTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.local_role = GroupFactory(name=ParkingPermitGroups.INSPECTORS)
        self.entra_role = GroupFactory(name=ParkingPermitGroups.SUPER_ADMIN)
        self.local_ad_group = ADGroupFactory()
        self.entra_ad_group = ADGroupFactory()
        ADGroupMapping.objects.create(
            ad_group=self.local_ad_group, group=self.local_role
        )
        ADGroupMapping.objects.create(
            ad_group=self.entra_ad_group, group=self.entra_role
        )

    def test_preserves_locally_assigned_role(self):
        self.user.groups.add(self.local_role)

        self.user.update_ad_groups([])

        self.assertTrue(self.user.is_inspectors)

    def test_does_not_grant_role_from_entra(self):
        self.user.update_ad_groups([self.entra_ad_group.name])

        self.assertFalse(self.user.is_super_admin)
        self.assertFalse(self.user.is_inspectors)

    def test_removed_local_role_is_not_restored_from_entra(self):
        self.user.groups.add(self.local_role)
        self.user.update_ad_groups([self.local_ad_group.name])
        self.user.groups.remove(self.local_role)

        self.user.update_ad_groups([self.local_ad_group.name])

        self.assertFalse(self.user.is_inspectors)

    def test_downgrading_role_is_not_reversed_from_entra(self):
        self.user.groups.add(self.entra_role)
        self.user.update_ad_groups([self.entra_ad_group.name])
        self.user.groups.set([self.local_role])

        self.user.update_ad_groups([self.entra_ad_group.name])

        self.assertFalse(self.user.is_super_admin)
        self.assertTrue(self.user.is_inspectors)

    @override_settings(LOCAL_ADMIN_ROLES_ENABLED=False)
    def test_flag_off_uses_entra_roles(self):
        self.user.groups.add(self.local_role)

        self.user.update_ad_groups([self.entra_ad_group.name])

        self.assertSetEqual(set(self.user.groups.all()), {self.entra_role})

    @override_settings(LOCAL_ADMIN_ROLES_ENABLED=False)
    def test_flag_off_removes_mapped_role_for_empty_claim(self):
        self.user.groups.add(self.local_role)

        self.user.update_ad_groups([])

        self.assertFalse(self.user.is_inspectors)

    def test_application_role_does_not_grant_django_admin_privileges(self):
        self.user.groups.add(self.entra_role)

        self.user.update_ad_groups([])
        self.user.refresh_from_db()

        self.assertTrue(self.user.is_super_admin)
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.is_staff)

    def test_django_superuser_does_not_grant_application_role(self):
        self.user.is_superuser = True
        self.user.save()

        self.assertFalse(self.user.is_super_admin)

    @override_settings(HELUSERS_ADGROUPS_CLAIM="ad_groups")
    def test_api_user_update_preserves_local_roles(self):
        self.user.groups.add(self.local_role)

        user = get_or_create_user(
            {
                "sub": str(self.user.uuid),
                "ad_groups": [self.entra_ad_group.name],
            },
            oidc=True,
        )

        self.assertEqual(user.pk, self.user.pk)
        self.assertTrue(user.is_inspectors)
        self.assertFalse(user.is_super_admin)
        self.assertTrue(user.ad_groups.filter(pk=self.entra_ad_group.pk).exists())

    @override_settings(HELUSERS_ADGROUPS_CLAIM="ad_groups")
    def test_browser_login_user_update_preserves_local_roles(self):
        self.user.groups.add(self.local_role)
        backend = SimpleNamespace(id_token={"ad_groups": [self.entra_ad_group.name]})

        result = create_or_update_user({}, backend, {}, uid=str(self.user.uuid))

        user = result["user"]
        self.assertEqual(user.pk, self.user.pk)
        self.assertTrue(user.is_inspectors)
        self.assertFalse(user.is_super_admin)

    def test_still_synchronizes_unrelated_groups(self):
        old_group = GroupFactory()
        new_group = GroupFactory()
        old_ad_group = ADGroupFactory()
        new_ad_group = ADGroupFactory()
        ADGroupMapping.objects.create(ad_group=old_ad_group, group=old_group)
        ADGroupMapping.objects.create(ad_group=new_ad_group, group=new_group)
        self.user.groups.add(self.local_role, old_group)

        self.user.update_ad_groups([new_ad_group.name])

        self.assertSetEqual(set(self.user.groups.all()), {self.local_role, new_group})

    def test_preserves_unmapped_groups(self):
        unrelated_group = GroupFactory()
        self.user.groups.add(unrelated_group)

        self.user.update_ad_groups([])

        self.assertTrue(self.user.groups.filter(pk=unrelated_group.pk).exists())


class UserModelTestCase(TestCase):
    def setUp(self):
        self.admin_group = GroupFactory(name=ParkingPermitGroups.SUPER_ADMIN)
        self.sanctions_and_refunds = GroupFactory(
            name=ParkingPermitGroups.SANCTIONS_AND_REFUNDS
        )
        self.sanctions = GroupFactory(name=ParkingPermitGroups.SANCTIONS)
        self.customer_service = GroupFactory(name=ParkingPermitGroups.CUSTOMER_SERVICE)
        self.preparators = GroupFactory(name=ParkingPermitGroups.PREPARATORS)
        self.inspectors = GroupFactory(name=ParkingPermitGroups.INSPECTORS)

    def test_is_super_admin(self):
        user = UserFactory()
        user.groups.add(self.admin_group)
        assert user.is_super_admin is True
        assert user.is_sanctions_and_refunds is True
        assert user.is_sanctions is True
        assert user.is_customer_service is True
        assert user.is_preparators is True
        assert user.is_inspectors is True

    def test_is_sanctions_and_refunds(self):
        user = UserFactory()
        user.groups.add(self.sanctions_and_refunds)
        assert user.is_super_admin is False
        assert user.is_sanctions_and_refunds is True
        assert user.is_sanctions is True
        assert user.is_customer_service is True
        assert user.is_preparators is True
        assert user.is_inspectors is True

    def test_is_sanctions(self):
        user = UserFactory()
        user.groups.add(self.sanctions)
        assert user.is_super_admin is False
        assert user.is_sanctions_and_refunds is False
        assert user.is_sanctions is True
        assert user.is_customer_service is True
        assert user.is_preparators is True
        assert user.is_inspectors is True

    def test_is_customer_service(self):
        user = UserFactory()
        user.groups.add(self.customer_service)
        assert user.is_super_admin is False
        assert user.is_sanctions_and_refunds is False
        assert user.is_sanctions is False
        assert user.is_customer_service is True
        assert user.is_preparators is True
        assert user.is_inspectors is True

    def test_is_preparators(self):
        user = UserFactory()
        user.groups.add(self.preparators)
        assert user.is_super_admin is False
        assert user.is_sanctions_and_refunds is False
        assert user.is_sanctions is False
        assert user.is_customer_service is False
        assert user.is_preparators is True
        assert user.is_inspectors is True

    def test_is_inspectors(self):
        user = UserFactory()
        user.groups.add(self.inspectors)
        assert user.is_super_admin is False
        assert user.is_sanctions_and_refunds is False
        assert user.is_sanctions is False
        assert user.is_customer_service is False
        assert user.is_preparators is False
        assert user.is_inspectors is True

    def test_if_no_valid_groups_it_should_return_false(self):
        user = UserFactory()
        assert user.is_super_admin is False
        assert user.is_sanctions_and_refunds is False
        assert user.is_sanctions is False
        assert user.is_customer_service is False
        assert user.is_preparators is False
        assert user.is_inspectors is False


class ParkingPermitGroupsOrderTestCase(TestCase):
    # The order is the privilege hierarchy, so a change here is a permission change.
    def test_groups_are_ordered_from_highest_to_lowest_privilege(self):
        assert ParkingPermitGroups.values == [
            "super_admin",
            "sanctions_and_refunds",
            "sanctions",
            "customer_service",
            "preparators",
            "inspectors",
        ]
