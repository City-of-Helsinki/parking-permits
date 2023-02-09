from django.test import TestCase

from users.models import ParkingPermitGroups
from users.tests.factories.user import GroupFactory, UserFactory


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
