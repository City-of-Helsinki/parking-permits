from datetime import datetime

from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from parking_permits.models.order import SubscriptionStatus
from parking_permits.models.parking_permit import ParkingPermitStatus
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import (
    OrderFactory,
    OrderItemFactory,
    SubscriptionFactory,
)
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory


class TestCustomer(TestCase):
    def test_anonymized_customer_cannot_be_anonymized(self):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory(is_anonymized=True)
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertFalse(customer.can_be_anonymized)

    def test_customer_modified_more_than_two_years_ago_can_be_anonymized(self):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory()
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertTrue(customer.can_be_anonymized)

    def test_customer_modified_recently_can_not_be_deleted(self):
        with freeze_time(timezone.make_aware(datetime(2021, 1, 1))):
            customer = CustomerFactory()
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31))):
            self.assertFalse(customer.can_be_anonymized)

    def test_customer_has_closed_permit_modified_more_than_two_years_ago_can_be_anonymized(
        self,
    ):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory()
            ParkingPermitFactory(customer=customer, status=ParkingPermitStatus.CLOSED)
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertTrue(customer.can_be_anonymized)

    def test_customer_has_end_time_recently_can_not_be_anonymized(self):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory()
            ParkingPermitFactory(
                customer=customer,
                status=ParkingPermitStatus.CLOSED,
                end_time=timezone.make_aware(datetime(2021, 12, 31)),
            )
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertFalse(customer.can_be_anonymized)

    def test_customer_has_valid_permit_can_not_be_anonymized(self):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory()
            ParkingPermitFactory(customer=customer, status=ParkingPermitStatus.VALID)
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertFalse(customer.can_be_anonymized)

    def test_customer_with_confirmed_subscription_can_not_be_anonymized(self):
        with freeze_time(timezone.make_aware(datetime(2020, 12, 31))):
            customer = CustomerFactory()
            subscription = SubscriptionFactory(status=SubscriptionStatus.CONFIRMED)
            order = OrderFactory(customer=customer)
            OrderItemFactory(
                order=order,
                subscription=subscription,
            )
        with freeze_time(timezone.make_aware(datetime(2022, 12, 31, 0, 0, 1))):
            self.assertFalse(customer.can_be_anonymized)
