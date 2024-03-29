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
    automatic_syncing_of_permits_to_parkkihubi,
)
from parking_permits.models import Customer
from parking_permits.models.parking_permit import (
    ContractType,
    ParkingPermit,
    ParkingPermitStatus,
)
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory


class CronTestCase(TestCase):
    def setUp(self):
        self.customer = CustomerFactory(first_name="Stephen", last_name="Strange")

    @patch("parking_permits.cron.sync_with_parkkihubi")
    def test_automatic_syncing_of_permits_to_parkkihubi_valid_not_synced(
        self, mock_sync
    ):
        ParkingPermitFactory(
            status=ParkingPermitStatus.VALID, synced_with_parkkihubi=False
        )
        automatic_syncing_of_permits_to_parkkihubi()
        mock_sync.assert_called()

    @patch("parking_permits.cron.sync_with_parkkihubi")
    def test_automatic_syncing_of_permits_to_parkkihubi_valid_is_synced(
        self, mock_sync
    ):
        ParkingPermitFactory(
            status=ParkingPermitStatus.VALID, synced_with_parkkihubi=True
        )
        automatic_syncing_of_permits_to_parkkihubi()
        mock_sync.assert_not_called()

    @patch("parking_permits.cron.sync_with_parkkihubi")
    def test_automatic_syncing_of_permits_to_parkkihubi_draft_not_synced(
        self, mock_sync
    ):
        ParkingPermitFactory(
            status=ParkingPermitStatus.DRAFT, synced_with_parkkihubi=False
        )
        automatic_syncing_of_permits_to_parkkihubi()
        mock_sync.assert_not_called()

    @patch("parking_permits.cron.sync_with_parkkihubi")
    def test_automatic_syncing_of_permits_to_parkkihubi_closed_not_synced(
        self, mock_sync
    ):
        ParkingPermitFactory(
            status=ParkingPermitStatus.CLOSED, synced_with_parkkihubi=False
        )
        automatic_syncing_of_permits_to_parkkihubi()
        mock_sync.assert_called()

    @freeze_time(tz.make_aware(datetime(2023, 11, 30, 0, 22)))
    def test_automatic_expiration_permits(self):
        ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 12, 1)),
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 11, 29)),
            status=ParkingPermitStatus.DRAFT,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 12, 1)),
            status=ParkingPermitStatus.DRAFT,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 11, 29)),
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 11, 29)),
            status=ParkingPermitStatus.CLOSED,
        )
        valid_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.VALID)
        draft_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.DRAFT)
        self.assertEqual(valid_permits.count(), 2)
        self.assertEqual(draft_permits.count(), 2)
        automatic_expiration_of_permits()
        closed_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.CLOSED)
        self.assertEqual(valid_permits.count(), 1)
        self.assertEqual(draft_permits.count(), 0)
        self.assertEqual(closed_permits.count(), 2)

    @freeze_time(tz.make_aware(datetime(2023, 11, 30, 0, 22)))
    def test_automatic_expiration_permits_with_primary_permit_change(self):
        first = ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 11, 29, 23, 59)),
            status=ParkingPermitStatus.VALID,
            primary_vehicle=True,
        )
        second = ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 12, 1, 23, 59)),
            status=ParkingPermitStatus.VALID,
            primary_vehicle=False,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 11, 29)),
            status=ParkingPermitStatus.DRAFT,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 12, 1)),
            status=ParkingPermitStatus.DRAFT,
        )
        valid_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.VALID)
        draft_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.DRAFT)
        closed_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.CLOSED)
        self.assertEqual(valid_permits.count(), 2)
        self.assertEqual(draft_permits.count(), 2)
        self.assertEqual(closed_permits.count(), 0)
        automatic_expiration_of_permits()
        self.assertEqual(valid_permits.all().count(), 1)
        valid_permit = valid_permits.first()
        self.assertEqual(valid_permit.id, second.id)
        self.assertEqual(valid_permit.primary_vehicle, True)
        self.assertEqual(draft_permits.all().count(), 0)
        closed_permits = closed_permits.all()
        self.assertEqual(closed_permits.count(), 1)
        closed_permit = closed_permits.first()
        self.assertEqual(closed_permit.id, first.id)
        self.assertEqual(
            closed_permit.end_time,
            tz.make_aware(datetime(2023, 11, 29, 23, 59, 59, 999999)),
        )

    @freeze_time(tz.make_aware(datetime(2023, 11, 30, 0, 22)))
    def test_automatic_expiration_permits_with_permit_vehicle_changed(self):
        ParkingPermitFactory(
            id=80000010,
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 12, 29, 23, 59)),
            vehicle_changed=True,
            vehicle_changed_date=tz.make_aware(datetime(2023, 11, 29)).date(),
            status=ParkingPermitStatus.VALID,
            primary_vehicle=True,
        )
        ParkingPermitFactory(
            id=80000020,
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 12, 29)),
            status=ParkingPermitStatus.VALID,
            primary_vehicle=False,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 11, 29)),
            status=ParkingPermitStatus.DRAFT,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2023, 12, 1)),
            status=ParkingPermitStatus.DRAFT,
        )
        valid_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.VALID)
        draft_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.DRAFT)
        closed_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.CLOSED)
        self.assertEqual(valid_permits.count(), 2)
        self.assertEqual(draft_permits.count(), 2)
        self.assertEqual(closed_permits.count(), 0)
        automatic_expiration_of_permits()
        valid_permits = valid_permits.all()
        self.assertEqual(valid_permits.count(), 1)
        valid_permit = valid_permits.first()
        self.assertEqual(valid_permit.id, 80000020)
        self.assertEqual(valid_permit.primary_vehicle, True)
        self.assertEqual(draft_permits.all().count(), 0)
        closed_permits = closed_permits.all()
        self.assertEqual(closed_permits.count(), 1)
        closed_permit = closed_permits.first()
        self.assertEqual(closed_permit.id, 80000010)
        self.assertEqual(
            closed_permit.end_time,
            tz.make_aware(datetime(2023, 11, 29, 23, 59, 59, 999999)),
        )


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
            contract_type=ContractType.FIXED_PERIOD,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 4, 6, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 3, 30, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 4, 13, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 4, 12, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.OPEN_ENDED,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 3, 31, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.CLOSED,
            contract_type=ContractType.FIXED_PERIOD,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=datetime(2023, 3, 31, tzinfo=dt_tz.utc),
            status=ParkingPermitStatus.CLOSED,
            contract_type=ContractType.OPEN_ENDED,
        )

    @freeze_time(tz.make_aware(datetime(2023, 3, 30)))
    @patch("parking_permits.services.mail.send_permit_email")
    def test_automatic_expiration_remind_targets(self, mock_method):
        mock_method.return_value = None
        valid_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.VALID)
        self.assertEqual(valid_permits.count(), 5)
        expiring_permits = automatic_expiration_remind_notification_of_permits()
        self.assertEqual(expiring_permits.count(), 2)
