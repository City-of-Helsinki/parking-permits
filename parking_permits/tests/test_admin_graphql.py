import json
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from helusers.authz import UserAuthorization
from helusers.oidc import AuthenticationError

import parking_permits.decorators
from parking_permits.admin_resolvers import (
    resolve_create_address,
    resolve_update_address,
    update_or_create_address,
)
from parking_permits.exceptions import AddressError
from parking_permits.models import Address
from parking_permits.models.parking_permit import (
    ParkingPermitEndType,
    ParkingPermitStatus,
)
from parking_permits.tests.factories.address import AddressFactory
from parking_permits.tests.factories.parking_permit import (
    CustomerFactory,
    ParkingPermitFactory,
)
from users.models import ParkingPermitGroups
from users.tests.factories.user import GroupFactory, UserFactory


class CurrentUserGroupsQueryTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        cls.groups = {
            role: GroupFactory(name=role.value) for role in ParkingPermitGroups
        }

    def setUp(self):
        authentication_patch = patch.object(
            parking_permits.decorators.RequestJWTAuthentication, "authenticate"
        )
        self.mock_authenticate = authentication_patch.start()
        self.addCleanup(authentication_patch.stop)
        self.mock_authenticate.return_value = UserAuthorization(self.user, {})

    def query_groups(self):
        return self.client.post(
            reverse("parking_permits:admin-graphql"),
            {"query": "{ currentUserGroups }"},
            content_type="application/json",
        )

    def test_returns_each_group_in_both_role_modes(self):
        for enabled in (False, True):
            for role in ParkingPermitGroups:
                with (
                    self.subTest(local_roles=enabled, role=role),
                    override_settings(LOCAL_ADMIN_ROLES_ENABLED=enabled),
                ):
                    self.user.groups.set([self.groups[role]])

                    response = self.query_groups()

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response.json(),
                        {"data": {"currentUserGroups": [role.value]}},
                    )

    def test_returns_all_assigned_parking_groups(self):
        self.user.groups.set(self.groups.values())

        response = self.query_groups()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"data": {"currentUserGroups": sorted(ParkingPermitGroups.values)}},
        )

    def test_authenticated_user_without_groups_can_query_own_groups(self):
        response = self.query_groups()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"data": {"currentUserGroups": []}})

    def test_excludes_unrelated_groups(self):
        self.user.groups.add(
            GroupFactory(), self.groups[ParkingPermitGroups.INSPECTORS]
        )

        response = self.query_groups()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"data": {"currentUserGroups": ["inspectors"]}}
        )

    def test_django_superuser_status_does_not_add_parking_groups(self):
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save()

        response = self.query_groups()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"data": {"currentUserGroups": []}})

    def test_reflects_group_changes_and_removal(self):
        assignments = [
            [ParkingPermitGroups.SUPER_ADMIN],
            [ParkingPermitGroups.INSPECTORS],
            [],
        ]
        for groups in assignments:
            with self.subTest(groups=groups):
                self.user.groups.set([self.groups[group] for group in groups])

                response = self.query_groups()

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json(), {"data": {"currentUserGroups": groups}}
                )

    def test_rejects_anonymous_requests(self):
        self.mock_authenticate.return_value = None

        response = self.query_groups()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"][0]["message"], "Forbidden")

    def test_rejects_failed_authentication(self):
        self.mock_authenticate.side_effect = AuthenticationError()

        response = self.query_groups()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"][0]["message"], "Forbidden")


permits_query = """
    query GetPermits(
        $pageInput: PageInput!
        $searchParams: PermitSearchParamsInput!
    ) {
        permits(
            pageInput: $pageInput
            searchParams: $searchParams
        ) {
            objects {
                customer {
                    firstName
                    lastName
                }
            }
            pageInfo {
                numPages
                next
                prev
            }
        }
    }
"""


class PermitsQueryTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client = Client()
        cls.default_variables = {
            "pageInput": {"page": 1},
            "searchParams": {"q": "John", "status": ParkingPermitStatus.DRAFT},
        }
        customer = CustomerFactory(first_name="John")
        ParkingPermitFactory(customer=customer)
        ParkingPermitFactory(customer=customer)
        ParkingPermitFactory(customer=customer)

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_return_parking_permits_list_for_super_admin(self, mock_authenticate):
        group = GroupFactory(name="super_admin")
        mock_admin = UserFactory(first_name="John")
        mock_admin.groups.add(group)
        mock_authenticate.return_value = UserAuthorization(mock_admin, {})
        url = reverse("parking_permits:admin-graphql")
        data = {
            "operationName": "GetPermits",
            "query": permits_query,
            "variables": self.default_variables,
        }
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(len(response_data["data"]["permits"]["objects"]), 3)
        expected_page_info = {"numPages": 1, "prev": None, "next": None}
        self.assertEqual(
            response_data["data"]["permits"]["pageInfo"], expected_page_info
        )

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_return_forbidden_for_non_super_admin(self, mock_authenticate):
        mock_admin = UserFactory()
        mock_authenticate.return_value = UserAuthorization(mock_admin, {})
        url = reverse("parking_permits:admin-graphql")
        data = {
            "operationName": "GetPermits",
            "query": permits_query,
            "variables": self.default_variables,
        }
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["errors"][0]["message"], "Forbidden")

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_return_forbidden_if_jwt_authentication_failed(self, mock_authenticate):
        mock_authenticate.side_effect = AuthenticationError()
        url = reverse("parking_permits:admin-graphql")
        data = {
            "operationName": "GetPermits",
            "query": permits_query,
            "variables": self.default_variables,
        }
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["errors"][0]["message"], "Forbidden")


customer_active_permits_query = """
    query GetPermits(
        $pageInput: PageInput!
        $searchParams: PermitSearchParamsInput!
    ) {
        permits(
            pageInput: $pageInput
            searchParams: $searchParams
        ) {
            objects {
                customer {
                    activePermits {
                        primaryVehicle
                        endTime
                        endType
                        contractType
                    }
                }
            }
        }
    }
"""


class CustomerActivePermitsQueryTestCase(TestCase):
    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_active_permits_expose_end_type(self, mock_authenticate):
        customer = CustomerFactory(first_name="John")
        ParkingPermitFactory(
            customer=customer,
            status=ParkingPermitStatus.VALID,
            end_type=ParkingPermitEndType.AFTER_CURRENT_PERIOD,
        )
        group = GroupFactory(name="super_admin")
        mock_admin = UserFactory()
        mock_admin.groups.add(group)
        mock_authenticate.return_value = UserAuthorization(mock_admin, {})
        data = {
            "operationName": "GetPermits",
            "query": customer_active_permits_query,
            "variables": {
                "pageInput": {"page": 1},
                "searchParams": {"q": "John", "status": ParkingPermitStatus.VALID},
            },
        }
        response = self.client.post(
            reverse("parking_permits:admin-graphql"),
            data,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertNotIn("errors", response_data)
        active_permits = response_data["data"]["permits"]["objects"][0]["customer"][
            "activePermits"
        ]
        self.assertEqual(len(active_permits), 1)
        self.assertEqual(
            active_permits[0]["endType"], ParkingPermitEndType.AFTER_CURRENT_PERIOD
        )


class ResolveCreateAddressTestCase(TestCase):
    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_resolve_create_address(self, mock_authenticate):
        """It should create a new address in the database."""

        result = resolve_create_address(
            None,
            _make_mock_info(_make_authenticated_request(mock_authenticate)),
            _address_info(),
        )
        self.assertEqual(result["success"], True)

        address = Address.objects.get()
        self.assertEqual(address.postal_code, "00580")

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_resolve_create_address_if_not_an_admin(self, mock_authenticate):
        """Only admins should be permitted to create a new address."""

        with self.assertRaises(PermissionDenied):
            resolve_create_address(
                None,
                _make_mock_info(
                    _make_authenticated_request(mock_authenticate, is_admin=False)
                ),
                _address_info(),
            )

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_resolve_create_address_with_duplicate_data(self, mock_authenticate):
        """It should raise an AddressError if the same street name, postal code and street number in the database."""

        AddressFactory(**_address_info(for_db=True))

        with self.assertRaises(AddressError):
            resolve_create_address(
                None,
                _make_mock_info(_make_authenticated_request(mock_authenticate)),
                _address_info(),
            )

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_resolve_create_address_with_duplicate_data_different_case(
        self, mock_authenticate
    ):
        """It should raise an IntegrityError if the same street name, postal code and street number in the database,
        even if these fields are in a different case."""

        AddressFactory(**_address_info(for_db=True))

        with self.assertRaises(AddressError):
            resolve_create_address(
                None,
                _make_mock_info(_make_authenticated_request(mock_authenticate)),
                _address_info(street_name="KÄsiVoide"),
            )


class ResolveUpdateAddressTestCase(TestCase):
    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_resolve_update_address(self, mock_authenticate):
        """It should update the address."""

        address = AddressFactory(postal_code="11111")

        result = resolve_update_address(
            None,
            _make_mock_info(_make_authenticated_request(mock_authenticate)),
            address.pk,
            _address_info(),
        )
        self.assertEqual(result["success"], True)

        address.refresh_from_db()
        self.assertEqual(address.postal_code, "00580")

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_resolve_update_address_if_not_an_admin(self, mock_authenticate):
        """Only admins should be permitted to update address."""

        with self.assertRaises(PermissionDenied):
            resolve_update_address(
                None,
                _make_mock_info(
                    _make_authenticated_request(mock_authenticate, is_admin=False)
                ),
                _address_info(),
            )

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_resolve_update_address_with_duplicate_data(self, mock_authenticate):
        AddressFactory(**_address_info(for_db=True))
        my_address = AddressFactory()

        with self.assertRaises(AddressError):
            resolve_update_address(
                None,
                _make_mock_info(_make_authenticated_request(mock_authenticate)),
                my_address.pk,
                _address_info(),
            )

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_resolve_update_address_with_duplicate_data_same_instance(
        self, mock_authenticate
    ):
        """It should be allowed to update with same fields on same instance."""

        address = AddressFactory(**_address_info(for_db=True))

        result = resolve_update_address(
            None,
            _make_mock_info(_make_authenticated_request(mock_authenticate)),
            address.pk,
            _address_info(),
        )
        self.assertEqual(result["success"], True)

        address.refresh_from_db()
        self.assertEqual(address.postal_code, "00580")


class UpdateOrCreateAddressTestCase(TestCase):
    def test_address_info_none(self):
        """Info is None, should just return None."""
        address = update_or_create_address(None)
        self.assertEqual(address, None)

    def test_new_address(self):
        """Should create a new address"""
        address = update_or_create_address(_address_info())

        self.assertEqual(Address.objects.count(), 1)
        self.assertEqual(address.postal_code, "00580")

    def test_new_address_with_another_existing(self):
        existing = AddressFactory(**_address_info(for_db=True))
        """Should still create a new address, if some key fields different."""
        address = update_or_create_address(_address_info(street_number="1/5"))
        assert address.pk != existing.pk

        self.assertEqual(Address.objects.count(), 2)
        self.assertEqual(address.postal_code, "00580")
        self.assertEqual(address.street_number, "1/5")

    def test_update_address(self):
        """If same matching address, should update and not create another."""
        address = AddressFactory(**_address_info(for_db=True))
        address = update_or_create_address(_address_info(city_sv="Stadi"))

        self.assertEqual(Address.objects.count(), 1)
        self.assertEqual(address.postal_code, "00580")
        self.assertEqual(address.city_sv, "Stadi")

    def test_update_address_case_insensitive(self):
        """Ensure we match address even if some key fields in different case."""
        address = AddressFactory(**_address_info(for_db=True))
        address = update_or_create_address(
            _address_info(street_name="KÄSIVOIDE", city_sv="Stadi")
        )

        self.assertEqual(Address.objects.count(), 1)
        # address should still be updated
        self.assertEqual(address.street_name, "KÄSIVOIDE")
        self.assertEqual(address.postal_code, "00580")
        self.assertEqual(address.city_sv, "Stadi")


def _make_authenticated_request(mock_authenticate, *, is_admin=True):
    user = UserFactory()

    if is_admin:
        admin_group = GroupFactory(name="super_admin")
        user.groups.add(admin_group)

    mock_authenticate.return_value = UserAuthorization(user, {})

    request = RequestFactory().post("/")
    request.user = user

    return request


def _make_mock_info(request):
    return Mock(context={"request": request})


def _address_info(*, for_db=False, **fields):
    """Create some dummy address data."""
    info = {
        "street_name": "Käsivoide",
        "street_number": "1/2",
        "street_name_sv": "Handkremsgatan",
        "city": "HELSINKI",
        "city_sv": "HELSINGFORS",
        "postal_code": "00580",
        "location": [24.95587348590678, 60.17392205331229],
        **fields,
    }
    if for_db:
        info["location"] = Point(*info["location"], srid=settings.SRID)

    return info
