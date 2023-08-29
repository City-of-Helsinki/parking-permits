import json
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory, TestCase
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
from parking_permits.models.parking_permit import ParkingPermitStatus
from parking_permits.tests.factories.address import AddressFactory
from parking_permits.tests.factories.parking_permit import (
    CustomerFactory,
    ParkingPermitFactory,
)
from users.tests.factories.user import GroupFactory, UserFactory

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
        self.assertEqual(response.status_code, 200)
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
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(response_data["errors"][0]["message"], "Forbidden")


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
