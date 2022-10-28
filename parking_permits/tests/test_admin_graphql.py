import json
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from helusers.authz import UserAuthorization
from helusers.oidc import AuthenticationError

import parking_permits.decorators
from parking_permits.models.parking_permit import ParkingPermitStatus
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
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
            "searchParams": {"q": "", "status": ParkingPermitStatus.DRAFT},
        }
        ParkingPermitFactory()
        ParkingPermitFactory()
        ParkingPermitFactory()

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_return_parking_permits_list_for_super_admin(self, mock_authenticate):
        group = GroupFactory(name="super_admin")
        mock_admin = UserFactory()
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
