from datetime import datetime
from datetime import timezone as dt_tz
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone as tz
from freezegun import freeze_time

from parking_permits.cron import (
    automatic_expiration_of_permits,
    automatic_expiration_remind_notification_of_permits,
    automatic_remove_obsolete_customer_data,
    automatic_syncing_of_permits_to_parkkihubi,
    handle_announcement_emails,
)
from parking_permits.models import Customer, Refund
from parking_permits.models.order import OrderStatus
from parking_permits.models.parking_permit import (
    ContractType,
    ParkingPermit,
    ParkingPermitEndType,
    ParkingPermitStatus,
)
from parking_permits.tests.factories import ParkingZoneFactory
from parking_permits.tests.factories.announcement import AnnouncementFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import OrderFactory, OrderItemFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory


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

    @freeze_time(tz.make_aware(datetime(2024, 11, 30, 0, 22)))
    def test_automatic_expiration_permits(self):
        ParkingPermitFactory(
            customer=self.customer,
            start_time=tz.make_aware(datetime(2024, 11, 2, 10, 0, 0)),
            end_time=tz.make_aware(datetime(2024, 12, 1, 23, 59, 59)),
            month_count=1,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=self.customer,
            start_time=tz.make_aware(datetime(2024, 10, 30, 10, 0, 0)),
            end_time=tz.make_aware(datetime(2024, 11, 29, 23, 59, 59)),
            month_count=1,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.DRAFT,
        )
        ParkingPermitFactory(
            customer=self.customer,
            start_time=tz.make_aware(datetime(2024, 11, 2, 10, 0, 0)),
            end_time=tz.make_aware(datetime(2024, 12, 1, 23, 59, 59)),
            month_count=1,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.DRAFT,
        )
        closable_permit_1 = ParkingPermitFactory(
            customer=self.customer,
            start_time=tz.make_aware(datetime(2024, 10, 29, 10, 0, 0)),
            end_time=tz.make_aware(datetime(2024, 11, 28, 23, 59, 59)),
            month_count=1,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.VALID,
        )
        closable_permit_2 = ParkingPermitFactory(
            customer=self.customer,
            start_time=tz.make_aware(datetime(2024, 9, 30, 10, 0, 0)),
            end_time=tz.make_aware(datetime(2024, 11, 29, 23, 59, 59)),
            month_count=2,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.VALID,
        )
        closable_permit_3 = ParkingPermitFactory(
            customer=self.customer,
            start_time=tz.make_aware(datetime(2024, 10, 30, 10, 0, 0)),
            end_time=tz.make_aware(datetime(2024, 11, 29, 23, 59, 59)),
            month_count=1,
            contract_type=ContractType.OPEN_ENDED,
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=self.customer,
            start_time=tz.make_aware(datetime(2024, 10, 30, 10, 0, 0)),
            end_time=tz.make_aware(datetime(2024, 11, 29, 23, 59, 59)),
            month_count=1,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.CLOSED,
        )
        valid_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.VALID)
        draft_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.DRAFT)
        closed_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.CLOSED)
        self.assertEqual(valid_permits.count(), 4)
        self.assertEqual(draft_permits.count(), 2)
        self.assertEqual(closed_permits.count(), 1)
        automatic_expiration_of_permits()
        self.assertEqual(valid_permits.count(), 1)
        self.assertEqual(draft_permits.count(), 0)
        self.assertEqual(closed_permits.count(), 4)
        closable_permit_1.refresh_from_db()
        self.assertEqual(
            closable_permit_1.end_time,
            tz.make_aware(datetime(2024, 11, 29, 23, 59, 59, 999999)),
        )
        self.assertEqual(
            closable_permit_1.end_type, ParkingPermitEndType.PREVIOUS_DAY_END
        )
        closable_permit_2.refresh_from_db()
        self.assertEqual(
            closable_permit_2.end_time,
            tz.make_aware(datetime(2024, 11, 29, 23, 59, 59, 999999)),
        )
        self.assertEqual(
            closable_permit_2.end_type, ParkingPermitEndType.PREVIOUS_DAY_END
        )
        closable_permit_3.refresh_from_db()
        self.assertEqual(
            closable_permit_3.end_time,
            tz.make_aware(datetime(2024, 11, 29, 23, 59, 59, 999999)),
        )
        self.assertEqual(
            closable_permit_3.end_type, ParkingPermitEndType.PREVIOUS_DAY_END
        )
        # Make sure that no refunds were created for these cases
        self.assertEqual(Refund.objects.count(), 0)

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

    @freeze_time(tz.make_aware(datetime(2024, 11, 30, 0, 22)))
    def test_automatic_expiration_permits_with_permit_vehicle_changed(self):
        permit_1 = ParkingPermitFactory(
            id=80000010,
            customer=self.customer,
            start_time=tz.make_aware(datetime(2024, 10, 30, 10, 0, 0)),
            end_time=tz.make_aware(datetime(2024, 12, 29, 23, 59, 59)),
            vehicle_changed=True,
            vehicle_changed_date=tz.make_aware(datetime(2024, 11, 29)).date(),
            month_count=2,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.VALID,
            primary_vehicle=True,
        )
        unit_price = Decimal(67.5)
        product = ProductFactory(
            unit_price=unit_price,
        )
        order = OrderFactory(
            customer=self.customer, status=OrderStatus.CONFIRMED, talpa_order_id=None
        )
        OrderItemFactory(
            order=order,
            permit=permit_1,
            start_time=tz.make_aware(datetime(2024, 10, 30, 10, 0, 0)),
            end_time=tz.make_aware(datetime(2024, 12, 29, 23, 59, 59)),
            product=product,
            unit_price=unit_price,
            payment_unit_price=unit_price,
            quantity=2,
            vat=Decimal(0.255),
        )
        permit_1.orders.add(order)
        ParkingPermitFactory(
            id=80000020,
            customer=self.customer,
            start_time=tz.make_aware(datetime(2024, 10, 30, 10, 0, 0)),
            end_time=tz.make_aware(datetime(2024, 12, 29, 23, 59, 59)),
            month_count=2,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.VALID,
            primary_vehicle=False,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2024, 11, 29)),
            status=ParkingPermitStatus.DRAFT,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=tz.make_aware(datetime(2024, 12, 1)),
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
        permit_1.refresh_from_db()
        closed_permit = permit_1
        self.assertEqual(closed_permit.id, 80000010)
        self.assertEqual(closed_permit.vehicle_changed, True)
        self.assertEqual(
            closed_permit.vehicle_changed_date,
            tz.make_aware(datetime(2024, 11, 29)).date(),
        )
        self.assertEqual(closed_permit.primary_vehicle, True)
        self.assertEqual(closed_permit.end_type, ParkingPermitEndType.PREVIOUS_DAY_END)
        self.assertEqual(
            closed_permit.end_time,
            tz.make_aware(datetime(2024, 11, 29, 23, 59, 59, 999999)),
        )
        self.assertEqual(Refund.objects.count(), 1)
        refund = Refund.objects.first()
        self.assertEqual(refund.amount, Decimal(67.5))  # Should be one month's amount


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


class AnnouncementEmailHandlingTestCase(TestCase):
    def setUp(self):
        self.zone_a = ParkingZoneFactory(name="A")
        self.zone_b = ParkingZoneFactory(name="B")
        self.zone_c = ParkingZoneFactory(name="C")
        self.announcement = AnnouncementFactory(subject_en="Test announcement")
        self.customer_1 = CustomerFactory(email="test@mail.com")
        self.customer_2 = CustomerFactory(email="test2@mail.com")
        self.customer_3 = CustomerFactory(email="test3@mail.com")

        self.customer_1_permit_1 = ParkingPermitFactory(
            customer=self.customer_1,
            parking_zone=self.zone_a,
            status=ParkingPermitStatus.VALID,
        )
        self.customer_1_permit_2 = ParkingPermitFactory(
            customer=self.customer_1,
            parking_zone=self.zone_a,
            status=ParkingPermitStatus.DRAFT,
        )
        self.customer_1_permit_3 = ParkingPermitFactory(
            customer=self.customer_1,
            parking_zone=self.zone_c,
            status=ParkingPermitStatus.CANCELLED,
        )
        self.customer_1_permit_4 = ParkingPermitFactory(
            customer=self.customer_1,
            parking_zone=self.zone_a,
            status=ParkingPermitStatus.VALID,
        )

        self.customer_2_permit_1 = ParkingPermitFactory(
            customer=self.customer_2,
            parking_zone=self.zone_b,
            status=ParkingPermitStatus.DRAFT,
        )
        self.customer_2_permit_2 = ParkingPermitFactory(
            customer=self.customer_2,
            parking_zone=self.zone_b,
            status=ParkingPermitStatus.VALID,
        )

        self.customer_3_permit_1 = ParkingPermitFactory(
            customer=self.customer_3,
            parking_zone=self.zone_c,
            status=ParkingPermitStatus.DRAFT,
        )

    def test_handle_announcement_emails(self):
        self.announcement._parking_zones.set([self.zone_a])
        self.assertEqual(self.announcement.emails_handled, False)
        handle_announcement_emails()
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue("Test announcement" in mail.outbox[0].subject)
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.emails_handled, True)

    def test_multizone_announcement(self):
        self.announcement._parking_zones.set([self.zone_a, self.zone_b])
        handle_announcement_emails()
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue("Test announcement" in mail.outbox[0].subject)
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.emails_handled, True)

    def test_valid_permits_only(self):
        self.announcement._parking_zones.set([self.zone_a, self.zone_b, self.zone_c])
        handle_announcement_emails()
        self.assertEqual(len(mail.outbox), 2)
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.emails_handled, True)

    def test_no_valid_permits(self):
        self.announcement._parking_zones.set([self.zone_c])
        handle_announcement_emails()
        self.assertEqual(len(mail.outbox), 0)
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.emails_handled, True)
