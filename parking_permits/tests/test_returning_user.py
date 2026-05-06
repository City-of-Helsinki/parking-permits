from datetime import datetime
from unittest.mock import patch

import freezegun
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone
from helusers.authz import UserAuthorization

import parking_permits.decorators
from audit_logger import AuditMsg
from parking_permits.models import Customer
from parking_permits.resolvers import resolve_user_profile
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.test_admin_graphql import _make_mock_info
from users.tests.factories.user import UserFactory

User = get_user_model()


class ReturningUserAfterAnonymizationTestCase(TestCase):
    REAL_SSN = "010101-123A"

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    @patch("parking_permits.resolvers.get_addresses")
    @patch("parking_permits.resolvers.HelsinkiProfile")
    def test_returning_user_creates_new_customer_after_old_user_deleted(
        self, mock_helsinki_profile, mock_get_addresses, mock_authenticate
    ):
        """
        Old User was deleted during anonymization -> Customer.user is null via
        SET_NULL. New login creates a fresh User and a fresh Customer.
        """
        mock_get_addresses.return_value = ({}, {})

        with freezegun.freeze_time(timezone.make_aware(datetime(2020, 1, 1))):
            old_customer = CustomerFactory(national_id_number=self.REAL_SSN)

        with freezegun.freeze_time(
            timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))
        ):
            old_customer.anonymize_all_data()

        old_customer.refresh_from_db()
        self.assertIsNone(old_customer.user_id)

        # Returning user logs in with a freshly-issued helusers User
        new_user = UserFactory()
        mock_helsinki_profile.return_value.get_customer.return_value = {
            "source_system": "HELSINKI_PROFILE",
            "source_id": "new-source",
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "phone_number": "+358000",
            "national_id_number": self.REAL_SSN,
        }

        mock_authenticate.return_value = UserAuthorization(new_user, {})
        request = RequestFactory().post("/")
        request.user = new_user
        info = _make_mock_info(request)

        new_customer = resolve_user_profile(None, info, audit_msg=AuditMsg("test"))

        # A new Customer was created (the old anonymized one had XX-ANON-...)
        self.assertEqual(
            Customer.objects.filter(national_id_number=self.REAL_SSN).count(), 1
        )

        self.assertNotEqual(new_customer.pk, old_customer.pk)
        self.assertEqual(new_customer.user_id, new_user.id)

    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    @patch("parking_permits.resolvers.get_addresses")
    @patch("parking_permits.resolvers.HelsinkiProfile")
    def test_returning_user_does_not_reuse_anonymized_customer(
        self,
        mock_helsinki_profile,
        mock_get_addresses,
        mock_authenticate,
    ):
        """The anonymized customer's SSN is XX-ANON-... so lookup by real SSN
        must miss it and create a new record."""
        mock_get_addresses.return_value = ({}, {})

        with freezegun.freeze_time(timezone.make_aware(datetime(2020, 1, 1))):
            old_customer = CustomerFactory(national_id_number=self.REAL_SSN)

        with freezegun.freeze_time(
            timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))
        ):
            old_customer.anonymize_all_data()

        new_user = UserFactory()
        mock_helsinki_profile.return_value.get_customer.return_value = {
            "source_system": "HELSINKI_PROFILE",
            "source_id": "src",
            "first_name": "A",
            "last_name": "B",
            "email": "a@b.c",
            "phone_number": "1",
            "national_id_number": self.REAL_SSN,
        }

        mock_authenticate.return_value = UserAuthorization(new_user, {})
        request = RequestFactory().post("/")
        request.user = new_user
        info = _make_mock_info(request)

        new_customer = resolve_user_profile(None, info, audit_msg=AuditMsg("test"))

        old_customer.refresh_from_db()
        self.assertNotEqual(new_customer.pk, old_customer.pk)
        self.assertTrue(old_customer.is_anonymized)
        self.assertFalse(new_customer.is_anonymized)
