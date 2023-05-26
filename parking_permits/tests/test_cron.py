from datetime import datetime
from datetime import timezone as dt_tz
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone as tz
from freezegun import freeze_time

from parking_permits.cron import (
    automatic_expiration_of_permits,
    automatic_expiration_remind_notification_of_permits,
    automatic_remove_obsolete_customer_data,
)
from parking_permits.models import Customer
from parking_permits.models.parking_permit import ParkingPermit, ParkingPermitStatus
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory


class CronTestCase(TestCase):
    def setUp(self):
        self.customer = CustomerFactory(first_name="Firstname A", last_name="")
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 3, 31, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 3, 29, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.DRAFT,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 3, 31, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.DRAFT,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 3, 29, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.VALID,
        )

    @freeze_time(tz.make_aware(datetime(2023, 3, 30)))
    def test_automatic_expiration_of_older_permits(self):
        valid_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.VALID)
        draft_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.DRAFT)
        self.assertEqual(valid_permits.count(), 2)
        self.assertEqual(draft_permits.count(), 2)

        automatic_expiration_of_permits()
        closed_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.CLOSED)
        self.assertEqual(valid_permits.count(), 1)
        self.assertEqual(draft_permits.count(), 2)
        self.assertEqual(closed_permits.count(), 1)


class AutomaticRemoveObsoleteCustomerDataTestCase(TestCase):
    def test_should_remove_obsolete_customers(self):
        with freeze_time(datetime(2020, 1, 1)):
            customer_1 = CustomerFactory()
            customer_2 = CustomerFactory()

        with freeze_time(datetime(2021, 1, 1)):
            customer_3 = CustomerFactory()
            ParkingPermitFactory(customer=customer_2)

        with freeze_time(datetime(2022, 1, 15)):
            automatic_remove_obsolete_customer_data()
            qs = Customer.objects.all()
            self.assertNotIn(customer_1, qs)
            self.assertIn(customer_2, qs)
            self.assertIn(customer_3, qs)


class AutomaticExpirationRemindPermitNotificationTestCase(TestCase):
    def setUp(self):
        self.customer = CustomerFactory(first_name="Firstname A", last_name="")
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 3, 31, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 4, 6, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 3, 30, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 4, 13, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 3, 31, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.CLOSED,
        )

    @freeze_time(tz.make_aware(datetime(2023, 3, 30)))
    @patch("parking_permits.services.mail.send_permit_email")
    def test_automatic_expiration_remind_targets(self, mock_method):
        mock_method.return_value = None
        valid_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.VALID)
        self.assertEqual(valid_permits.count(), 4)
        expiring_permits = automatic_expiration_remind_notification_of_permits()
        self.assertEqual(expiring_permits.count(), 2)
