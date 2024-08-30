from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from freezegun import freeze_time

from parking_permits.models import Order, Refund
from parking_permits.models.order import OrderStatus, OrderType, SubscriptionStatus
from parking_permits.models.parking_permit import (
    ContractType,
    ParkingPermitEndType,
    ParkingPermitStatus,
)
from parking_permits.models.product import Product, ProductType
from parking_permits.resolver_utils import (
    create_fixed_period_refunds,
    end_permit,
    end_permits,
)
from parking_permits.tests.factories import ParkingZoneFactory
from parking_permits.tests.factories.order import OrderItemFactory, SubscriptionFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import (
    TemporaryVehicleFactory,
    VehicleFactory,
    VehiclePowerTypeFactory,
)

IBAN = "12345678"

MOCK_SYNC_WITH_PARKKIHUBI = "parking_permits.resolver_utils.sync_with_parkkihubi"

MOCK_VALIDATE_ORDER = "parking_permits.models.order.OrderValidator.validate_order"

MOCK_SEND_PERMIT_EMAIL = "parking_permits.resolver_utils.send_permit_email"

MOCK_SEND_VEHICLE_DISCOUNT_EMAIL = (
    "parking_permits.resolver_utils.send_vehicle_low_emission_discount_email"
)

MOCK_SEND_REFUND_EMAIL = "parking_permits.resolver_utils.send_refund_email"


@pytest.fixture()
def zone():
    return ParkingZoneFactory(name="A")


class TestEndPermits:
    @pytest.fixture()
    def current_datetime(self):
        return timezone.make_aware(datetime(2024, 3, 26, 0, 0))

    @pytest.mark.django_db()
    @patch(MOCK_SYNC_WITH_PARKKIHUBI)
    @patch(MOCK_VALIDATE_ORDER)
    @patch(MOCK_SEND_PERMIT_EMAIL)
    @patch(MOCK_SEND_VEHICLE_DISCOUNT_EMAIL)
    @patch(MOCK_SEND_REFUND_EMAIL)
    def test_end_open_ended_permit_with_subscription(
        self,
        mock_send_refund_email,
        mock_send_vehicle_discount_email,
        mock_send_permit_email,
        mock_validate_order,
        mock_sync_with_parkkihubi,
        current_datetime,
    ):
        with freeze_time(current_datetime):
            subscription = SubscriptionFactory()

            permit = ParkingPermitFactory(
                contract_type=ContractType.OPEN_ENDED,
                status=ParkingPermitStatus.VALID,
                month_count=1,
            )

            OrderItemFactory(permit=permit, subscription=subscription)

            end_permits(
                permit.customer.user,
                permit,
                end_type=ParkingPermitEndType.IMMEDIATELY,
                iban=IBAN,
                cancel_from_talpa=False,
            )

        subscription.refresh_from_db()

        assert subscription.status == SubscriptionStatus.CANCELLED

        permit.refresh_from_db()

        assert permit.status == ParkingPermitStatus.CLOSED

        mock_sync_with_parkkihubi.assert_called()
        mock_validate_order.assert_called()
        mock_send_permit_email.assert_called()
        mock_send_vehicle_discount_email.assert_not_called()
        mock_send_refund_email.assert_not_called()

    @pytest.mark.django_db()
    @patch(MOCK_SYNC_WITH_PARKKIHUBI)
    @patch(MOCK_SEND_PERMIT_EMAIL)
    @patch(MOCK_SEND_VEHICLE_DISCOUNT_EMAIL)
    @patch(MOCK_SEND_REFUND_EMAIL)
    def test_fixed_period_permit(
        self,
        mock_send_refund_email,
        mock_send_vehicle_discount_email,
        mock_send_permit_email,
        mock_sync_with_parkkihubi,
        current_datetime,
        zone,
    ):
        with freeze_time(current_datetime):
            start_time = timezone.make_aware(datetime(2024, 1, 1))
            end_time = timezone.make_aware(datetime(2024, 6, 30))

            _create_zone_products(
                zone,
                [
                    [
                        (start_time.date(), end_time.date()),
                        Decimal("30"),
                    ],
                ],
            )

            permit = ParkingPermitFactory(
                contract_type=ContractType.FIXED_PERIOD,
                status=ParkingPermitStatus.VALID,
                start_time=start_time,
                end_time=end_time,
                month_count=12,
                parking_zone=zone,
            )

            order = Order.objects.create_for_permits([permit])
            order.status = OrderStatus.CONFIRMED
            order.save()

            end_permits(
                permit.customer.user,
                permit,
                end_type=ParkingPermitEndType.IMMEDIATELY,
                iban=IBAN,
            )

        permit.refresh_from_db()

        assert permit.status == ParkingPermitStatus.CLOSED

        refund = Refund.objects.get(order=order)

        # 3 months unused at 30 EUR/month
        assert refund.amount == 90

        mock_sync_with_parkkihubi.assert_called()
        mock_send_permit_email.assert_called()
        mock_send_vehicle_discount_email.assert_not_called()
        mock_send_refund_email.assert_called()

    @pytest.mark.django_db()
    @patch(MOCK_SYNC_WITH_PARKKIHUBI)
    @patch(MOCK_SEND_PERMIT_EMAIL)
    @patch(MOCK_SEND_VEHICLE_DISCOUNT_EMAIL)
    @patch(MOCK_SEND_REFUND_EMAIL)
    def test_multiple_fixed_period_permit(
        self,
        mock_send_refund_email,
        mock_send_vehicle_discount_email,
        mock_send_permit_email,
        mock_sync_with_parkkihubi,
        current_datetime,
        zone,
    ):
        with freeze_time(current_datetime):
            start_time = timezone.make_aware(datetime(2024, 1, 1))
            end_time = timezone.make_aware(datetime(2024, 6, 30))

            _create_zone_products(
                zone,
                [
                    [
                        (start_time.date(), end_time.date()),
                        Decimal("30"),
                    ],
                ],
            )

            permit_a = ParkingPermitFactory(
                contract_type=ContractType.FIXED_PERIOD,
                status=ParkingPermitStatus.VALID,
                start_time=start_time,
                end_time=timezone.make_aware(datetime(2024, 4, 30)),
                month_count=12,
                parking_zone=zone,
            )
            permit_b = ParkingPermitFactory(
                contract_type=ContractType.FIXED_PERIOD,
                status=ParkingPermitStatus.VALID,
                start_time=timezone.make_aware(datetime(2024, 5, 1)),
                end_time=end_time,
                month_count=12,
                parking_zone=zone,
                customer=permit_a.customer,
            )

            permits = [permit_a, permit_b]

            order = Order.objects.create_for_permits(permits)
            order.status = OrderStatus.CONFIRMED
            order.save()

            end_permits(
                permit_a.customer.user,
                *[permit_a, permit_b],
                force_end=True,
                end_type=ParkingPermitEndType.IMMEDIATELY,
                iban=IBAN,
            )

        permit_a.refresh_from_db()
        assert permit_a.status == ParkingPermitStatus.CLOSED

        permit_b.refresh_from_db()
        assert permit_b.status == ParkingPermitStatus.CLOSED

        refund = Refund.objects.get(order=order)

        # 3 months unused at 30 EUR/month
        assert refund.amount == 90

        mock_sync_with_parkkihubi.assert_called()
        mock_send_permit_email.assert_called()
        mock_send_vehicle_discount_email.assert_not_called()
        mock_send_refund_email.assert_called()


class TestEndPermit:
    @pytest.mark.django_db()
    @patch(MOCK_SYNC_WITH_PARKKIHUBI)
    @patch(MOCK_SEND_PERMIT_EMAIL)
    @patch(MOCK_SEND_VEHICLE_DISCOUNT_EMAIL)
    @patch(MOCK_VALIDATE_ORDER)
    def test_end_open_ended_permit_with_subscription(
        self,
        mock_validate_order,
        mock_send_vehicle_discount_email,
        mock_send_permit_email,
        mock_sync_with_parkkihubi,
    ):
        subscription = SubscriptionFactory()

        permit = ParkingPermitFactory(
            contract_type=ContractType.OPEN_ENDED,
            status=ParkingPermitStatus.VALID,
            month_count=1,
        )

        OrderItemFactory(permit=permit, subscription=subscription)

        end_permit(
            permit.customer.user,
            permit,
            ParkingPermitEndType.IMMEDIATELY,
            iban=IBAN,
            cancel_from_talpa=False,
        )

        subscription.refresh_from_db()

        assert subscription.status == SubscriptionStatus.CANCELLED

        permit.refresh_from_db()

        assert permit.status == ParkingPermitStatus.CLOSED

        mock_sync_with_parkkihubi.assert_called()
        mock_validate_order.assert_called()
        mock_send_permit_email.assert_called()
        mock_send_vehicle_discount_email.assert_not_called()

    @pytest.mark.django_db()
    @patch(MOCK_VALIDATE_ORDER)
    @patch(MOCK_SYNC_WITH_PARKKIHUBI)
    @patch(MOCK_SEND_PERMIT_EMAIL)
    @patch(MOCK_SEND_VEHICLE_DISCOUNT_EMAIL)
    def test_end_fixed_term_permit(
        self,
        mock_send_vehicle_discount_email,
        mock_send_permit_email,
        mock_sync_with_parkkihubi,
        mock_validate_order,
    ):
        permit = ParkingPermitFactory(
            contract_type=ContractType.OPEN_ENDED,
            status=ParkingPermitStatus.VALID,
            month_count=12,
        )

        order = OrderItemFactory(permit=permit).order

        # add a temp vehicle

        temp_vehicle = TemporaryVehicleFactory(is_active=True)
        permit.temp_vehicles.add(temp_vehicle)

        end_permit(
            permit.customer.user,
            permit,
            ParkingPermitEndType.IMMEDIATELY,
            iban=IBAN,
            cancel_from_talpa=False,
        )

        permit.refresh_from_db()

        order.refresh_from_db()
        assert order.status == OrderStatus.CANCELLED

        temp_vehicle.refresh_from_db()
        assert temp_vehicle.is_active is False

        mock_sync_with_parkkihubi.assert_called()
        mock_validate_order.assert_called()
        mock_send_permit_email.assert_called()
        mock_send_vehicle_discount_email.assert_not_called()

    @pytest.mark.django_db()
    @patch(MOCK_SYNC_WITH_PARKKIHUBI)
    @patch(MOCK_SEND_PERMIT_EMAIL)
    @patch(MOCK_SEND_VEHICLE_DISCOUNT_EMAIL)
    @patch(MOCK_VALIDATE_ORDER)
    def test_send_low_emission_discount_email(
        self,
        mock_validate_order,
        mock_send_vehicle_discount_email,
        mock_send_permit_email,
        mock_sync_with_parkkihubi,
    ):
        low_emission_vehicle = VehicleFactory(
            power_type=VehiclePowerTypeFactory(identifier="04", name="Electric"),
            consent_low_emission_accepted=True,
        )

        permit = ParkingPermitFactory(
            contract_type=ContractType.OPEN_ENDED,
            status=ParkingPermitStatus.VALID,
            month_count=12,
            vehicle=low_emission_vehicle,
        )

        OrderItemFactory(permit=permit)

        end_permit(
            permit.customer.user,
            permit,
            ParkingPermitEndType.IMMEDIATELY,
            iban=IBAN,
            cancel_from_talpa=False,
        )

        permit.refresh_from_db()

        assert permit.status == ParkingPermitStatus.CLOSED

        mock_validate_order.assert_called()
        mock_sync_with_parkkihubi.assert_called()
        mock_send_permit_email.assert_called()
        mock_send_vehicle_discount_email.assert_called()


class TestCreateRefund:
    @pytest.mark.django_db()
    @patch(MOCK_SEND_REFUND_EMAIL)
    def test_new_refund_fixed_period(self, mock_send_refund_email, zone):
        with freeze_time("2024-3-26"):
            start_time = timezone.make_aware(datetime(2024, 1, 1))
            end_time = timezone.make_aware(datetime(2024, 6, 30))

            _create_zone_products(
                zone,
                [
                    [
                        (start_time.date(), end_time.date()),
                        Decimal("60"),
                    ],
                ],
            )

            permit = ParkingPermitFactory(
                contract_type=ContractType.FIXED_PERIOD,
                status=ParkingPermitStatus.VALID,
                start_time=start_time,
                end_time=end_time,
                month_count=6,
                parking_zone=zone,
            )

            order = Order.objects.create_for_permits([permit])
            order.status = OrderStatus.CONFIRMED
            order.save()

            refunds = create_fixed_period_refunds(
                permit.customer.user,
                permit,
                iban=IBAN,
            )

        assert refunds != []

        # 3 months unused at 60 EUR/month
        assert refunds[0].amount == 180

        mock_send_refund_email.assert_called()

    @pytest.mark.django_db()
    @patch(MOCK_SEND_REFUND_EMAIL)
    def test_new_refund_open_ended(self, mock_send_refund_email, zone):
        with freeze_time("2024-3-26"):
            start_time = timezone.make_aware(datetime(2024, 1, 1))
            end_time = timezone.make_aware(datetime(2024, 6, 30))

            _create_zone_products(
                zone,
                [
                    [
                        (start_time.date(), end_time.date()),
                        Decimal("60"),
                    ],
                ],
            )

            permit = ParkingPermitFactory(
                contract_type=ContractType.OPEN_ENDED,
                status=ParkingPermitStatus.VALID,
                start_time=start_time,
                end_time=end_time,
                month_count=1,
                parking_zone=zone,
            )

            order = Order.objects.create_for_permits([permit])
            order.status = OrderStatus.CONFIRMED
            order.save()

            refunds = create_fixed_period_refunds(
                permit.customer.user,
                permit,
                iban=IBAN,
            )

        assert refunds == []

        mock_send_refund_email.assert_not_called()

    @pytest.mark.django_db()
    @patch(MOCK_SEND_REFUND_EMAIL)
    def test_new_refund_multiple_permits(self, mock_send_refund_email, zone):
        with freeze_time("2024-3-26"):
            start_time = timezone.make_aware(datetime(2024, 1, 1))
            end_time = timezone.make_aware(datetime(2024, 6, 30))

            _create_zone_products(
                zone,
                [
                    [
                        (start_time.date(), end_time.date()),
                        Decimal("60"),
                    ],
                ],
            )

            permit_a = ParkingPermitFactory(
                contract_type=ContractType.FIXED_PERIOD,
                status=ParkingPermitStatus.VALID,
                start_time=start_time,
                end_time=timezone.make_aware(datetime(2024, 4, 30)),
                month_count=4,
                parking_zone=zone,
            )
            permit_b = ParkingPermitFactory(
                contract_type=ContractType.FIXED_PERIOD,
                status=ParkingPermitStatus.VALID,
                start_time=timezone.make_aware(datetime(2024, 5, 1)),
                end_time=end_time,
                month_count=2,
                parking_zone=zone,
                customer=permit_a.customer,
            )

            permits = [permit_a, permit_b]

            order = Order.objects.create_for_permits(permits)
            order.status = OrderStatus.CONFIRMED
            order.save()

            refunds = create_fixed_period_refunds(
                permit_a.customer.user,
                *permits,
                iban=IBAN,
            )

        assert refunds != []

        # 3 months unused at 60 EUR/month
        assert refunds[0].amount == 180

        mock_send_refund_email.assert_called()

    @pytest.mark.django_db()
    @patch(MOCK_SEND_REFUND_EMAIL)
    def test_new_refund_with_permit_extension_request(
        self, mock_send_refund_email, zone
    ):
        with freeze_time("2024-3-26"):
            start_time = timezone.make_aware(datetime(2024, 1, 1))
            end_time = timezone.make_aware(datetime(2024, 12, 31))

            _create_zone_products(
                zone,
                [
                    [
                        (start_time.date(), end_time.date()),
                        Decimal("60"),
                    ],
                ],
            )

            permit = ParkingPermitFactory(
                contract_type=ContractType.FIXED_PERIOD,
                status=ParkingPermitStatus.VALID,
                start_time=start_time,
                end_time=timezone.make_aware(datetime(2024, 4, 30)),
                month_count=4,
                parking_zone=zone,
            )
            order = Order.objects.create_for_permits([permit])
            order.status = OrderStatus.CONFIRMED
            order.save()

            ext_request_order = Order.objects.create_for_extended_permit(
                permit,
                2,
                status=OrderStatus.CONFIRMED,
                type=OrderType.CREATED,
            )
            ext_request = permit.permit_extension_requests.create(
                order=ext_request_order,
                month_count=2,
            )
            # approve and extend permit immediately
            ext_request.approve()

            refunds = create_fixed_period_refunds(
                permit.customer.user,
                permit,
                iban=IBAN,
            )
            assert refunds != []

            refund = refunds[0]
            #  1. order: 1 month unused at 60 EUR/month
            #  2. extension request order: 2 months unused at 60 EUR/month
            #  total: 180 EUR
            assert refund.amount == 180
            delta = Decimal(0.01)
            assert refund.vat == pytest.approx(Decimal(0.24), delta)
            assert refund.vat_percent == pytest.approx(Decimal(24.0), delta)
            assert refund.vat_amount == pytest.approx(Decimal(34.84), delta)

            mock_send_refund_email.assert_called

    @pytest.mark.django_db()
    @patch(MOCK_SEND_REFUND_EMAIL)
    def test_new_multiple_vat_refunds_with_permit_extension_request(
        self, mock_send_refund_email, zone
    ):
        with freeze_time("2024-3-26"):
            start_time = timezone.make_aware(datetime(2024, 1, 1))
            end_time = timezone.make_aware(datetime(2024, 12, 31))

            _create_zone_products(
                zone,
                [
                    [
                        (start_time.date(), end_time.date()),
                        Decimal("60"),
                    ],
                ],
            )

            permit = ParkingPermitFactory(
                contract_type=ContractType.FIXED_PERIOD,
                status=ParkingPermitStatus.VALID,
                start_time=start_time,
                end_time=timezone.make_aware(datetime(2024, 4, 30)),
                month_count=4,
                parking_zone=zone,
            )
            order = Order.objects.create_for_permits([permit])
            order.status = OrderStatus.CONFIRMED
            order.save()

            for product in Product.objects.all():
                product.vat = Decimal("0.255")
                product.save()

            ext_request_order = Order.objects.create_for_extended_permit(
                permit,
                2,
                status=OrderStatus.CONFIRMED,
                type=OrderType.CREATED,
            )

            ext_request = permit.permit_extension_requests.create(
                order=ext_request_order,
                month_count=2,
            )
            # approve and extend permit immediately
            ext_request.approve()

            refunds = create_fixed_period_refunds(
                permit.customer.user,
                permit,
                iban=IBAN,
            )
            assert refunds != []

            # 2 refunds with different vat
            assert len(refunds) == 2
            #  1. order: 1 month unused at 60 EUR/month = 60 EUR, VAT 24%
            refund = refunds[0]
            assert refund.amount == 60
            delta = Decimal(0.01)
            assert refund.vat == pytest.approx(Decimal(0.24), delta)
            assert refund.vat_percent == pytest.approx(Decimal(24.0), delta)
            assert refund.vat_amount == pytest.approx(Decimal(11.61), delta)
            #  2. extension request order: 2 months unused at 60 EUR/month = 120 EUR, VAT 25.5%
            second_refund = refunds[1]
            assert second_refund.amount == 120
            assert second_refund.vat == pytest.approx(Decimal(0.255), delta)
            assert second_refund.vat_percent == pytest.approx(Decimal(25.5), delta)
            assert second_refund.vat_amount == pytest.approx(Decimal(24.38), delta)

            mock_send_refund_email.assert_called

    @pytest.mark.django_db()
    @patch(MOCK_SEND_REFUND_EMAIL)
    def test_not_refundable(self, mock_send_refund_email, zone):
        with freeze_time("2024-3-26"):
            start_time = timezone.make_aware(datetime(2024, 1, 1))
            end_time = timezone.make_aware(datetime(2024, 6, 30))

            _create_zone_products(
                zone,
                [
                    [
                        (start_time.date(), end_time.date()),
                        Decimal("60"),
                    ],
                ],
            )

            permit = ParkingPermitFactory(
                contract_type=ContractType.FIXED_PERIOD,
                status=ParkingPermitStatus.CANCELLED,
                start_time=start_time,
                end_time=end_time,
                month_count=12,
                parking_zone=zone,
            )

            order = Order.objects.create_for_permits([permit])
            order.status = OrderStatus.CONFIRMED
            order.save()

            refunds = create_fixed_period_refunds(
                permit.customer.user,
                permit,
                iban=IBAN,
            )

        assert refunds == []

        mock_send_refund_email.assert_not_called()

    @pytest.mark.django_db()
    @patch(MOCK_SEND_REFUND_EMAIL)
    def test_refundable_amount_zero(self, mock_send_refund_email, zone):
        with freeze_time("2024-3-26"):
            start_time = timezone.make_aware(datetime(2024, 1, 1))
            end_time = timezone.make_aware(datetime(2024, 6, 30))

            _create_zone_products(
                zone,
                [
                    [
                        (start_time.date(), end_time.date()),
                        Decimal("0"),
                    ],
                ],
            )

            permit = ParkingPermitFactory(
                contract_type=ContractType.FIXED_PERIOD,
                status=ParkingPermitStatus.VALID,
                start_time=start_time,
                end_time=end_time,
                month_count=12,
                parking_zone=zone,
            )

            order = Order.objects.create_for_permits([permit])
            order.status = OrderStatus.CONFIRMED
            order.save()

            refunds = create_fixed_period_refunds(
                permit.customer.user,
                permit,
                iban=IBAN,
            )

        assert refunds == []

        mock_send_refund_email.assert_not_called()


def _create_zone_products(zone, product_detail_list):
    products = []
    for date_range, unit_price in product_detail_list:
        start_date, end_date = date_range
        product = ProductFactory(
            zone=zone,
            type=ProductType.RESIDENT,
            start_date=start_date,
            end_date=end_date,
            unit_price=unit_price,
            vat=Decimal("0.24"),
        )
        products.append(product)
    return products
