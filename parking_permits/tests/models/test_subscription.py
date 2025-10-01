import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.urls import reverse, reverse_lazy
from freezegun import freeze_time

from parking_permits.models.order import (
    Order,
    SubscriptionStatus,
)
from parking_permits.models.parking_permit import (
    ParkingPermitStatus,
)
from parking_permits.models.refund import Refund
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import (
    OrderItemFactory,
    SubscriptionFactory,
)
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.zone import ParkingZoneFactory
from parking_permits.tests.test_resolver_utils import _create_zone_products

MOCK_SYNC_WITH_PARKKIHUBI = "parking_permits.resolver_utils.sync_with_parkkihubi"

MOCK_VALIDATE_ORDER = "parking_permits.models.order.OrderValidator.validate_order"

MOCK_SEND_PERMIT_EMAIL = "parking_permits.resolver_utils.send_permit_email"

MOCK_SEND_VEHICLE_DISCOUNT_EMAIL = (
    "parking_permits.resolver_utils.send_vehicle_low_emission_discount_email"
)


def get_validated_order_data(talpa_order_id, talpa_order_item_id):
    return {
        "orderId": talpa_order_id,
        "checkoutUrl": "https://test.com",
        "loggedInCheckoutUrl": "https://test.com",
        "receiptUrl": "https://test.com",
        "items": [
            {
                "orderItemId": talpa_order_item_id,
                "startDate": "2023-04-01T15:46:05.619",
                "priceGross": "45.00",
                "rowPriceTotal": "45.00",
                "vatPercentage": "25.50",
                "quantity": 1,
            }
        ],
    }


class TestSubscriptionTestCase(TestCase):
    @pytest.mark.django_db()
    @patch(MOCK_SYNC_WITH_PARKKIHUBI)
    @patch(MOCK_SEND_PERMIT_EMAIL)
    @patch(MOCK_SEND_VEHICLE_DISCOUNT_EMAIL)
    @patch(MOCK_VALIDATE_ORDER)
    def test_subscription_cancel_does_not_generate_additional_zero_refund(
        self,
        mock_validate_order,
        mock_send_vehicle_discount_email,
        mock_send_permit_email,
        mock_sync_with_parkkihubi,
    ):
        talpa_order_id = "d86ca61d-97e9-410a-a1e3-4894873b1b35"
        talpa_order_item_id = "2f20c06d-2a9a-4a60-be4b-504d8a2f8c02"
        talpa_subscription_id = "f769b803-0bd0-489d-aa81-b35af391f391"

        zone = ParkingZoneFactory(name="A")

        customer = CustomerFactory()
        permit_start_time = datetime.datetime(
            2023, 4, 30, 10, 00, 0, tzinfo=datetime.timezone.utc
        )
        permit_end_time = permit_start_time + relativedelta(months=1)
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            customer=customer,
            parking_zone=zone,
            start_time=permit_start_time,
            end_time=permit_end_time,
            month_count=1,
        )

        unit_price = Decimal(45)
        products_start_date = permit_start_time.date() - relativedelta(years=1)
        products_end_date = permit_start_time.date() + relativedelta(years=5)
        products = _create_zone_products(
            zone,
            [
                [
                    (products_start_date, products_end_date),
                    unit_price,
                ],
            ],
        )

        subscription = SubscriptionFactory(
            talpa_subscription_id=talpa_subscription_id,
            status=SubscriptionStatus.CONFIRMED,
        )

        initial_order = Order.objects.create_for_permits([permit])
        initial_order.save()

        initial_order_item = OrderItemFactory(
            talpa_order_item_id=talpa_order_id,
            order=initial_order,
            product=products[0],
            permit=permit,
            subscription=subscription,
            start_time=permit_start_time,
            end_time=permit_end_time,
        )

        mock_validate_order.return_value = get_validated_order_data(
            talpa_order_id, talpa_order_item_id
        )

        with freeze_time(permit_start_time + relativedelta(days=20)):
            # Renew subscription
            order_view_url = reverse("parking_permits:order-notify")
            subscription_renewal_data = {
                "eventType": "SUBSCRIPTION_RENEWAL_ORDER_CREATED",
                "subscriptionId": talpa_subscription_id,
                "orderId": talpa_order_id,
            }
            response = self.client.post(order_view_url, subscription_renewal_data)
            self.assertEqual(response.status_code, 200)

        with freeze_time(permit_start_time + relativedelta(days=20, minutes=5)):
            # Subscription renewal payment
            payment_view_url = reverse_lazy("parking_permits:payment-notify")
            renewal_payment_data = {
                "eventType": "PAYMENT_PAID",
                "orderId": talpa_order_id,
            }
            response = self.client.post(payment_view_url, renewal_payment_data)
            self.assertEqual(response.status_code, 200)

        # There should be no refunds before ending the permit.
        refund_count_before_end = Refund.objects.count()
        self.assertEqual(refund_count_before_end, 0)

        # Cancel sub/end the permit, do this early enough to trigger a refund.
        with freeze_time(permit_start_time + relativedelta(days=20, minutes=6)):
            subscription_cancel_view_url = reverse(
                "parking_permits:subscription-notify"
            )
            subscription_cancel_data = {
                "eventType": "SUBSCRIPTION_CANCELLED",
                "subscriptionId": talpa_subscription_id,
                "orderId": talpa_order_id,
                "orderItemId": talpa_order_item_id,
            }

            response = self.client.post(
                subscription_cancel_view_url, subscription_cancel_data
            )
            self.assertEqual(response.status_code, 200)

        # Initial order item should not have refunds due to the logic
        # in subscription cancellation being run immediately after the
        # usual refund-logic when ending a permit.
        initial_order_item.refresh_from_db()
        order_item_refunds = initial_order_item.order.refunds.all()
        self.assertEqual(order_item_refunds.count(), 0)

        # The usual refunds are created before the sub is cancelled,
        # these should have positive amount.
        refunds_after_end = permit.refunds.all()
        assert refunds_after_end.count() > 0
        for refund in refunds_after_end:
            assert refund.amount > 0

        subscription.refresh_from_db()
        assert subscription.status == SubscriptionStatus.CANCELLED

        # VALID due to subscription cancellation using
        # AFTER_CURRENT_PERIOD as the end type.
        permit.refresh_from_db()
        assert permit.status == ParkingPermitStatus.VALID

        mock_sync_with_parkkihubi.assert_called()
        mock_validate_order.assert_called()
        mock_send_permit_email.assert_called()
        mock_send_vehicle_discount_email.assert_not_called()
