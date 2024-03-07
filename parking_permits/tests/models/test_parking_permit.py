from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.test import TestCase, override_settings
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from freezegun import freeze_time

from parking_permits.exceptions import (
    ParkkihubiPermitError,
    PermitCanNotBeEnded,
    ProductCatalogError,
)
from parking_permits.models import Order, ParkingPermitExtensionRequest
from parking_permits.models.order import OrderStatus
from parking_permits.models.parking_permit import (
    ContractType,
    ParkingPermitEndType,
    ParkingPermitStatus,
)
from parking_permits.models.product import ProductType
from parking_permits.models.vehicle import EmissionType
from parking_permits.tests.factories import ParkingZoneFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import OrderFactory, OrderItemFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.permit_extension_request import (
    ParkingPermitExtensionRequestFactory,
)
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import (
    LowEmissionCriteriaFactory,
    TemporaryVehicleFactory,
    VehicleFactory,
    VehiclePowerTypeFactory,
)
from parking_permits.tests.models.test_product import MockResponse
from parking_permits.utils import get_end_time

CURRENT_YEAR = date.today().year


class ParkingZoneTestCase(TestCase):
    maxDiff = None

    def setUp(self):
        self.customer = CustomerFactory()
        self.zone_a = ParkingZoneFactory(name="A")
        self.zone_b = ParkingZoneFactory(name="B")

    def _create_zone_products(self, zone, product_detail_list):
        products = []
        for date_range, unit_price in product_detail_list:
            start_date, end_date = date_range
            product = ProductFactory(
                zone=zone,
                type=ProductType.RESIDENT,
                start_date=start_date,
                end_date=end_date,
                unit_price=unit_price,
            )
            products.append(product)
        return products

    @freeze_time(timezone.make_aware(datetime(2021, 11, 15)))
    def test_should_return_correct_months_used(self):
        start_time = timezone.now()
        end_time = get_end_time(start_time, 1)

        open_ended_started_immediately = ParkingPermitFactory(
            contract_type=ContractType.OPEN_ENDED,
            start_time=start_time,
            end_time=end_time,
        )

        self.assertEqual(open_ended_started_immediately.months_used, 1)

        start_time = timezone.make_aware(datetime(2021, 9, 15))
        end_time = get_end_time(start_time, 6)
        fixed_period_permit_started_2_months_ago = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        self.assertEqual(fixed_period_permit_started_2_months_ago.months_used, 3)

        start_time = timezone.make_aware(datetime(2021, 11, 16))
        end_time = get_end_time(start_time, 6)
        fixed_period_permit_start_tomorrow = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        self.assertEqual(fixed_period_permit_start_tomorrow.months_used, 0)

        start_time = timezone.make_aware(datetime(2019, 11, 15))
        end_time = get_end_time(start_time, 6)
        fixed_period_permit_started_2_years_ago = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        self.assertEqual(fixed_period_permit_started_2_years_ago.months_used, 6)

        start_time = timezone.make_aware(datetime(2019, 11, 15))
        open_ended_permit_started_two_years_ago = ParkingPermitFactory(
            contract_type=ContractType.OPEN_ENDED,
            start_time=start_time,
        )
        self.assertEqual(open_ended_permit_started_two_years_ago.months_used, 25)

    @freeze_time(timezone.make_aware(datetime(2024, 1, 1)))
    def test_can_end_after_current_period_end_time_fixed_period(self):
        start_time = timezone.make_aware(datetime(2024, 1, 1))
        end_time = get_end_time(start_time, 6)
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        self.assertTrue(permit.can_end_after_current_period)

    @freeze_time(timezone.make_aware(datetime(2024, 1, 1)))
    def test_can_end_after_current_period_end_time_fixed_period_current_period_end_time_gt_end_time(
        self,
    ):
        start_time = timezone.make_aware(datetime(2023, 11, 1))
        end_time = get_end_time(start_time, 1)
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=3,
        )
        self.assertFalse(permit.can_end_after_current_period)

    @freeze_time(timezone.make_aware(datetime(2024, 1, 1)))
    def test_can_end_after_current_period_end_time_open_ended(self):
        start_time = timezone.make_aware(datetime(2024, 1, 1))
        end_time = get_end_time(start_time, 1)
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.OPEN_ENDED,
            start_time=start_time,
            end_time=end_time,
            month_count=1,
        )
        self.assertTrue(permit.can_end_after_current_period)

    @freeze_time(timezone.make_aware(datetime(2021, 11, 15)))
    def test_should_return_correct_months_left(self):
        start_time = timezone.make_aware(datetime(2021, 9, 15))
        end_time = get_end_time(start_time, 6)
        fixed_period_permit_started_2_months_ago = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        self.assertEqual(fixed_period_permit_started_2_months_ago.months_left, 3)

        start_time = timezone.make_aware(datetime(2021, 11, 16))
        end_time = get_end_time(start_time, 6)
        fixed_period_permit_start_tomorrow = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        self.assertEqual(fixed_period_permit_start_tomorrow.months_left, 6)

        start_time = timezone.make_aware(datetime(2019, 11, 15))
        end_time = get_end_time(start_time, 6)
        fixed_period_permit_started_2_years_ago = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        self.assertEqual(fixed_period_permit_started_2_years_ago.months_left, 0)

        start_time = timezone.make_aware(datetime(2019, 11, 15))
        open_ended_permit_started_two_years_ago = ParkingPermitFactory(
            contract_type=ContractType.OPEN_ENDED,
            start_time=start_time,
        )
        self.assertEqual(open_ended_permit_started_two_years_ago.months_left, None)

    @freeze_time(timezone.make_aware(datetime(2022, 1, 20)))
    def test_should_return_correct_end_time_of_current_time(self):
        start_time = timezone.make_aware(datetime(2022, 1, 20))
        end_time = get_end_time(start_time, 1)
        permit = ParkingPermitFactory(
            contract_type=ContractType.OPEN_ENDED,
            start_time=start_time,
            end_time=end_time,
            month_count=1,
        )

        self.assertEqual(
            permit.end_time,
            permit.current_period_end_time,
        )

        self.assertEqual(
            permit.current_period_end_time,
            timezone.make_aware(datetime(2022, 2, 19, 23, 59, 59, 999999)),
        )

        start_time = timezone.make_aware(datetime(2021, 11, 15))
        end_time = get_end_time(start_time, 6)
        permit = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        self.assertEqual(
            permit.current_period_end_time,
            timezone.make_aware(datetime(2022, 2, 14, 23, 59, 59, 999999)),
        )

        start_time = timezone.make_aware(datetime(2021, 11, 20))
        end_time = get_end_time(start_time, 6)
        permit = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        self.assertEqual(
            permit.current_period_end_time,
            timezone.make_aware(datetime(2022, 2, 19, 23, 59, 59, 999999)),
        )

    @freeze_time(timezone.make_aware(datetime(2021, 11, 20, 12, 10, 50)))
    def test_should_cancel_all_extensions_on_end_permit(self):
        start_time = timezone.make_aware(datetime(2021, 11, 15))
        end_time = get_end_time(start_time, 6)
        permit = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        approved = ParkingPermitExtensionRequestFactory(
            permit=permit, status=ParkingPermitExtensionRequest.Status.APPROVED
        )
        pending = ParkingPermitExtensionRequestFactory(
            permit=permit, status=ParkingPermitExtensionRequest.Status.PENDING
        )

        permit.end_permit(ParkingPermitEndType.IMMEDIATELY)

        approved.refresh_from_db()
        assert approved.is_approved()

        pending.refresh_from_db()
        assert pending.is_cancelled()

    @freeze_time(timezone.make_aware(datetime(2021, 11, 20, 12, 10, 50)))
    def test_should_set_end_time_to_now_if_end_permit_immediately(self):
        start_time = timezone.make_aware(datetime(2021, 11, 15))
        end_time = get_end_time(start_time, 6)
        permit = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        permit.end_permit(ParkingPermitEndType.IMMEDIATELY)
        self.assertEqual(
            permit.end_time, timezone.make_aware(datetime(2021, 11, 20, 12, 10, 50))
        )

    @freeze_time(timezone.make_aware(datetime(2021, 11, 20, 12, 10, 50)))
    def test_should_set_end_time_to_period_end_if_end_permit_after_current_period(self):
        start_time = timezone.make_aware(datetime(2021, 11, 15))
        end_time = get_end_time(start_time, 6)
        permit = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=6,
        )
        permit.end_permit(ParkingPermitEndType.AFTER_CURRENT_PERIOD)
        self.assertEqual(
            permit.end_time,
            timezone.make_aware(datetime(2021, 12, 14, 23, 59, 59, 999999)),
        )

    @freeze_time(timezone.make_aware(datetime(2021, 11, 20, 12, 10, 50)))
    def test_should_raise_error_when_end_primary_vehicle_permit_with_active_secondary_vehicle_permit(
        self,
    ):
        primary_start_time = timezone.make_aware(datetime(2021, 11, 15))
        primary_end_time = get_end_time(primary_start_time, 6)
        primary_vehicle_permit = ParkingPermitFactory(
            customer=self.customer,
            primary_vehicle=True,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.VALID,
            start_time=primary_start_time,
            end_time=primary_end_time,
            month_count=6,
        )
        secondary_start_time = timezone.make_aware(datetime(CURRENT_YEAR, 1, 1))
        secondary_end_time = get_end_time(secondary_start_time, 2)
        ParkingPermitFactory(
            customer=self.customer,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.VALID,
            start_time=secondary_start_time,
            end_time=secondary_end_time,
            month_count=2,
        )
        with self.assertRaises(PermitCanNotBeEnded):
            primary_vehicle_permit.end_permit(ParkingPermitEndType.AFTER_CURRENT_PERIOD)

    def test_get_refund_amount_for_unused_items_should_return_correct_total(self):
        product_detail_list = [
            [(date(2021, 1, 1), date(2021, 6, 30)), Decimal("20")],
            [(date(2021, 7, 1), date(2021, 12, 31)), Decimal("30")],
        ]
        self._create_zone_products(self.zone_a, product_detail_list)
        start_time = timezone.make_aware(datetime(2021, 1, 1))
        end_time = get_end_time(start_time, 12)
        permit = ParkingPermitFactory(
            customer=self.customer,
            parking_zone=self.zone_a,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=12,
        )
        order = Order.objects.create_for_permits([permit])
        order.status = OrderStatus.CONFIRMED
        order.save()
        permit.refresh_from_db()
        permit.status = ParkingPermitStatus.VALID
        permit.save()

        with freeze_time(datetime(2021, 4, 15)):
            refund_amount = permit.get_refund_amount_for_unused_items()
            self.assertEqual(refund_amount, Decimal("220"))

    def test_get_products_with_quantities_should_return_a_single_product_for_open_ended(
        self,
    ):
        product_detail_list = [[(date(2021, 1, 1), date(2021, 12, 31)), Decimal("30")]]
        self._create_zone_products(self.zone_a, product_detail_list)
        start_time = timezone.make_aware(datetime(2021, 2, 15))
        permit = ParkingPermitFactory(
            parking_zone=self.zone_a,
            contract_type=ContractType.OPEN_ENDED,
            start_time=start_time,
            month_count=1,
        )
        products = permit.get_products_with_quantities()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0][1], 1)

    def test_get_products_with_quantities_raise_error_when_no_product_available_for_open_ended(
        self,
    ):
        zone = ParkingZoneFactory()
        start_time = timezone.make_aware(datetime(2021, 2, 15))
        permit = ParkingPermitFactory(
            parking_zone=zone,
            contract_type=ContractType.OPEN_ENDED,
            start_time=start_time,
            month_count=1,
        )
        with self.assertRaises(ProductCatalogError):
            permit.get_products_with_quantities()

    def test_get_products_with_quantities_raise_error_when_multiple_products_available_for_open_ended(
        self,
    ):
        product_detail_list = [
            [(date(2021, 1, 1), date(2021, 6, 30)), Decimal("30")],
            [(date(2021, 5, 1), date(2021, 12, 31)), Decimal("30")],
        ]
        self._create_zone_products(self.zone_a, product_detail_list)
        start_time = timezone.make_aware(datetime(2021, 6, 15))
        permit = ParkingPermitFactory(
            parking_zone=self.zone_a,
            contract_type=ContractType.OPEN_ENDED,
            start_time=start_time,
            month_count=1,
        )
        with self.assertRaises(ProductCatalogError):
            permit.get_products_with_quantities()

    def test_get_products_with_quantities_should_return_products_with_quantities_for_fix_period(
        self,
    ):
        product_detail_list = [
            [(date(2021, 1, 1), date(2021, 5, 31)), Decimal("30")],
            [(date(2021, 6, 1), date(2021, 7, 31)), Decimal("30")],
            [(date(2021, 8, 1), date(2021, 12, 31)), Decimal("30")],
        ]
        products = self._create_zone_products(self.zone_a, product_detail_list)
        start_time = timezone.make_aware(datetime(2021, 2, 15))
        end_time = get_end_time(start_time, 10)  # ends at 2021-2-14, 23:59
        permit = ParkingPermitFactory(
            parking_zone=self.zone_a,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=10,
        )
        products_with_quantities = permit.get_products_with_quantities()
        self.assertEqual(products_with_quantities[0][0].id, products[0].id)
        self.assertEqual(products_with_quantities[0][1], 4)
        self.assertEqual(products_with_quantities[1][0].id, products[1].id)
        self.assertEqual(products_with_quantities[1][1], 2)
        self.assertEqual(products_with_quantities[2][0].id, products[2].id)
        self.assertEqual(products_with_quantities[2][1], 4)

    @freeze_time(timezone.make_aware(datetime(2024, 1, 1)))
    def test_active_temporary_vehicles_active_in_time_range(self):
        vehicle = TemporaryVehicleFactory(
            start_time=datetime(2023, 12, 20),
            end_time=datetime(2024, 1, 29),
            is_active=True,
        )
        permit = ParkingPermitFactory()
        permit.temp_vehicles.add(vehicle)
        self.assertEqual(permit.active_temporary_vehicle, vehicle)

    @freeze_time(timezone.make_aware(datetime(2024, 1, 1)))
    def test_active_temporary_vehicles_not_active(self):
        vehicle = TemporaryVehicleFactory(
            start_time=datetime(2023, 12, 20),
            end_time=datetime(2024, 1, 29),
            is_active=False,
        )
        permit = ParkingPermitFactory()
        permit.temp_vehicles.add(vehicle)
        self.assertEqual(permit.active_temporary_vehicle, None)

    @freeze_time(timezone.make_aware(datetime(2024, 1, 1)))
    def test_active_temporary_vehicles_not_in_time_range(self):
        vehicle = TemporaryVehicleFactory(
            start_time=datetime(2024, 1, 3),
            end_time=datetime(2024, 1, 29),
            is_active=True,
        )
        permit = ParkingPermitFactory()
        permit.temp_vehicles.add(vehicle)
        self.assertEqual(permit.active_temporary_vehicle, None)

    def test_get_products_with_quantities_should_return_products_with_quantities_for_fix_period_with_mid_month_start(
        self,
    ):
        product_detail_list = [
            [(date(2021, 1, 10), date(2021, 5, 9)), Decimal("30")],
            [(date(2021, 5, 10), date(2021, 8, 9)), Decimal("30")],
            [(date(2021, 8, 10), date(2021, 12, 31)), Decimal("30")],
        ]
        products = self._create_zone_products(self.zone_a, product_detail_list)
        start_time = timezone.make_aware(datetime(2021, 2, 15))
        end_time = get_end_time(start_time, 10)  # ends at 2021-2-14, 23:59
        permit = ParkingPermitFactory(
            parking_zone=self.zone_a,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=10,
        )
        products_with_quantities = permit.get_products_with_quantities()
        self.assertEqual(products_with_quantities[0][0].id, products[0].id)
        self.assertEqual(products_with_quantities[0][1], 3)
        self.assertEqual(products_with_quantities[1][0].id, products[1].id)
        self.assertEqual(products_with_quantities[1][1], 3)
        self.assertEqual(products_with_quantities[2][0].id, products[2].id)
        self.assertEqual(products_with_quantities[2][1], 4)

    def test_get_products_with_quantities_should_raise_error_when_products_does_not_cover_permit_duration(
        self,
    ):
        product_detail_list = [
            [(date(2021, 1, 10), date(2021, 5, 9)), Decimal("30")],
            [(date(2021, 5, 10), date(2021, 10, 9)), Decimal("30")],
        ]
        self._create_zone_products(self.zone_a, product_detail_list)
        start_time = timezone.make_aware(datetime(2021, 2, 15))
        end_time = get_end_time(start_time, 10)  # ends at 2021-2-14, 23:59
        permit = ParkingPermitFactory(
            parking_zone=self.zone_a,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=10,
        )
        with self.assertRaises(ProductCatalogError):
            permit.get_products_with_quantities()

    @freeze_time("2021-01-01")
    def test_get_unused_order_items_for_open_ended_permit(self):
        product_detail_list = [
            [(date(2021, 1, 1), date(2021, 6, 30)), Decimal("30")],
        ]
        self._create_zone_products(self.zone_a, product_detail_list)
        start_time = timezone.make_aware(datetime(2021, 1, 1))
        permit = ParkingPermitFactory(
            customer=self.customer,
            parking_zone=self.zone_a,
            contract_type=ContractType.OPEN_ENDED,
            start_time=start_time,
            month_count=12,
        )
        Order.objects.create_for_permits([permit])
        permit.refresh_from_db()
        permit.status = ParkingPermitStatus.VALID
        permit.save()

        unused_items = permit.get_unused_order_items()
        unused_item, quantity, (start_date, end_date) = unused_items[0]

        self.assertEqual(unused_item.unit_price, Decimal("30.00"))
        self.assertEqual(quantity, 1)
        self.assertEqual(start_date, date(2021, 1, 1))
        self.assertEqual(end_date, date(2021, 1, 31))

    def test_get_unused_order_items_return_unused_items(self):
        product_detail_list = [
            [(date(2021, 1, 1), date(2021, 6, 30)), Decimal("20")],
            [(date(2021, 7, 1), date(2021, 12, 31)), Decimal("30")],
        ]
        self._create_zone_products(self.zone_a, product_detail_list)
        start_time = timezone.make_aware(datetime(2021, 1, 1))
        end_time = get_end_time(start_time, 12)
        permit = ParkingPermitFactory(
            customer=self.customer,
            parking_zone=self.zone_a,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=start_time,
            end_time=end_time,
            month_count=12,
        )
        Order.objects.create_for_permits([permit])
        permit.refresh_from_db()
        permit.status = ParkingPermitStatus.VALID
        permit.save()

        with freeze_time(datetime(2021, 4, 15)):
            unused_items = permit.get_unused_order_items()
            self.assertEqual(len(unused_items), 2)
            self.assertEqual(unused_items[0][0].unit_price, Decimal("20"))
            self.assertEqual(unused_items[0][1], 2)
            self.assertEqual(unused_items[0][2], (date(2021, 5, 1), date(2021, 6, 30)))
            self.assertEqual(unused_items[1][0].unit_price, Decimal("30"))
            self.assertEqual(unused_items[1][1], 6)
            self.assertEqual(unused_items[1][2], (date(2021, 7, 1), date(2021, 12, 31)))

    def test_open_ended_parking_permit_change_price_list_when_prices_go_down(self):
        zone_a_product_list = [
            [(date(2021, 1, 1), date(2021, 6, 30)), Decimal("20")],
        ]
        self._create_zone_products(self.zone_a, zone_a_product_list)
        high_emission_vehicle = VehicleFactory()

        start_time = timezone.make_aware(datetime(2021, 4, 15))
        end_time = timezone.make_aware(datetime(2021, 5, 14))

        permit = ParkingPermitFactory(
            customer=self.customer,
            parking_zone=self.zone_a,
            vehicle=high_emission_vehicle,
            contract_type=ContractType.OPEN_ENDED,
            status=ParkingPermitStatus.VALID,
            start_time=start_time,
            end_time=end_time,
            month_count=12,
        )
        # starting immediately
        with freeze_time(datetime(2021, 4, 15)):
            with translation.override("fi"):
                price_change_list = permit.get_price_change_list(self.zone_a, True)
                self.assertEqual(len(price_change_list), 1)
                self.assertEqual(
                    price_change_list[0]["product"], f'{_("Parking zone")} A'
                )
                self.assertEqual(price_change_list[0]["previous_price"], Decimal("20"))
                self.assertEqual(price_change_list[0]["new_price"], Decimal("10"))
                self.assertEqual(
                    price_change_list[0]["price_change"], Decimal("-10.00")
                )
                self.assertEqual(
                    price_change_list[0]["price_change_vat"], Decimal("-1.9355")
                )
                self.assertEqual(price_change_list[0]["month_count"], 0)
                self.assertEqual(price_change_list[0]["start_date"], date(2021, 5, 15))
                self.assertEqual(price_change_list[0]["end_date"], date(2021, 6, 14))

    def test_open_ended_parking_permit_change_price_list_when_prices_go_down_end_date_in_month(
        self,
    ):
        zone_a_product_list = [
            [(date(2021, 1, 1), date(2021, 6, 30)), Decimal("20")],
        ]
        self._create_zone_products(self.zone_a, zone_a_product_list)
        high_emission_vehicle = VehicleFactory()

        start_time = timezone.make_aware(datetime(2021, 4, 15))
        end_time = timezone.make_aware(datetime(2021, 5, 15))
        permit = ParkingPermitFactory(
            customer=self.customer,
            parking_zone=self.zone_a,
            vehicle=high_emission_vehicle,
            contract_type=ContractType.OPEN_ENDED,
            status=ParkingPermitStatus.VALID,
            start_time=start_time,
            end_time=end_time,
            month_count=12,
        )
        # starting immediately
        with freeze_time(datetime(2021, 4, 15)):
            with translation.override("fi"):
                price_change_list = permit.get_price_change_list(self.zone_a, True)
                self.assertEqual(len(price_change_list), 1)
                self.assertEqual(
                    price_change_list[0]["product"], f'{_("Parking zone")} A'
                )
                self.assertEqual(price_change_list[0]["previous_price"], Decimal("20"))
                self.assertEqual(price_change_list[0]["new_price"], Decimal("10"))
                self.assertEqual(
                    price_change_list[0]["price_change"], Decimal("-10.00")
                )
                self.assertEqual(
                    price_change_list[0]["price_change_vat"], Decimal("-1.9355")
                )
                self.assertEqual(price_change_list[0]["month_count"], 1)
                self.assertEqual(price_change_list[0]["start_date"], date(2021, 5, 15))
                self.assertEqual(price_change_list[0]["end_date"], date(2021, 6, 14))

    def test_parking_permit_change_price_list_when_prices_go_down(self):
        zone_a_product_list = [
            [(date(2021, 1, 1), date(2021, 6, 30)), Decimal("20")],
            [(date(2021, 7, 1), date(2021, 12, 31)), Decimal("30")],
        ]
        self._create_zone_products(self.zone_a, zone_a_product_list)
        zone_b_product_list = [
            [(date(2021, 1, 1), date(2021, 6, 30)), Decimal("30")],
            [(date(2021, 7, 1), date(2021, 12, 31)), Decimal("40")],
        ]
        self._create_zone_products(self.zone_b, zone_b_product_list)
        high_emission_vehicle = VehicleFactory()

        start_time = timezone.make_aware(datetime(2021, 1, 1))
        end_time = get_end_time(start_time, 12)
        permit = ParkingPermitFactory(
            customer=self.customer,
            parking_zone=self.zone_a,
            vehicle=high_emission_vehicle,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.VALID,
            start_time=start_time,
            end_time=end_time,
            month_count=12,
        )
        with freeze_time(datetime(2021, 4, 15)):
            with translation.override("fi"):
                price_change_list = permit.get_price_change_list(self.zone_b, True)
                self.assertEqual(len(price_change_list), 2)
                self.assertEqual(
                    price_change_list[0]["product"], f'{_("Parking zone")} B'
                )
                self.assertEqual(price_change_list[0]["previous_price"], Decimal("20"))
                self.assertEqual(price_change_list[0]["new_price"], Decimal("15"))
                self.assertEqual(price_change_list[0]["price_change"], Decimal("-5"))
                self.assertEqual(
                    price_change_list[0]["price_change_vat"], Decimal("-0.9677")
                )
                self.assertEqual(price_change_list[0]["month_count"], 2)
                self.assertEqual(price_change_list[0]["start_date"], date(2021, 5, 1))
                self.assertEqual(price_change_list[0]["end_date"], date(2021, 6, 30))
                self.assertEqual(
                    price_change_list[1]["product"], f'{_("Parking zone")} B'
                )
                self.assertEqual(price_change_list[1]["previous_price"], Decimal("30"))
                self.assertEqual(price_change_list[1]["new_price"], Decimal("20"))
                self.assertEqual(price_change_list[1]["price_change"], Decimal("-10"))
                self.assertEqual(
                    price_change_list[1]["price_change_vat"], Decimal("-1.9355")
                )
                self.assertEqual(price_change_list[1]["month_count"], 6)
                self.assertEqual(price_change_list[1]["start_date"], date(2021, 7, 1))
                self.assertEqual(price_change_list[1]["end_date"], date(2021, 12, 31))

    def test_parking_permit_change_price_list_when_prices_go_up(self):
        zone_a_product_list = [
            [(date(CURRENT_YEAR, 1, 1), date(CURRENT_YEAR, 6, 30)), Decimal("20")],
            [(date(CURRENT_YEAR, 7, 1), date(CURRENT_YEAR, 12, 31)), Decimal("30")],
        ]
        self._create_zone_products(self.zone_a, zone_a_product_list)
        zone_b_product_list = [
            [(date(CURRENT_YEAR, 1, 1), date(CURRENT_YEAR, 6, 30)), Decimal("30")],
            [(date(CURRENT_YEAR, 7, 1), date(CURRENT_YEAR, 12, 31)), Decimal("40")],
        ]
        self._create_zone_products(self.zone_b, zone_b_product_list)

        start_time = timezone.make_aware(datetime(CURRENT_YEAR, 1, 1))
        end_time = get_end_time(start_time, 12)

        low_emission_vehicle = VehicleFactory(
            power_type=VehiclePowerTypeFactory(identifier="01", name="Bensin"),
            emission=70,
            euro_class=6,
            emission_type=EmissionType.WLTP,
        )
        LowEmissionCriteriaFactory(
            start_date=start_time,
            end_date=end_time,
            nedc_max_emission_limit=None,
            wltp_max_emission_limit=80,
            euro_min_class_limit=6,
        )

        permit = ParkingPermitFactory(
            customer=self.customer,
            parking_zone=self.zone_a,
            vehicle=low_emission_vehicle,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.VALID,
            start_time=start_time,
            end_time=end_time,
            month_count=12,
        )
        with freeze_time(datetime(CURRENT_YEAR, 4, 15)):
            with translation.override("fi"):
                price_change_list = permit.get_price_change_list(self.zone_b, False)
                self.assertEqual(len(price_change_list), 2)
                self.assertEqual(
                    price_change_list[0]["product"], f'{_("Parking zone")} B'
                )
                self.assertEqual(price_change_list[0]["previous_price"], Decimal("10"))
                self.assertEqual(price_change_list[0]["new_price"], Decimal("30"))
                self.assertEqual(price_change_list[0]["price_change"], Decimal("20"))
                self.assertEqual(
                    price_change_list[0]["price_change_vat"], Decimal("3.8710")
                )
                self.assertEqual(price_change_list[0]["month_count"], 2)
                self.assertEqual(
                    price_change_list[0]["start_date"], date(CURRENT_YEAR, 5, 1)
                )
                self.assertEqual(
                    price_change_list[0]["end_date"], date(CURRENT_YEAR, 6, 30)
                )
                self.assertEqual(
                    price_change_list[1]["product"], f'{_("Parking zone")} B'
                )
                self.assertEqual(price_change_list[1]["previous_price"], Decimal("15"))
                self.assertEqual(price_change_list[1]["new_price"], Decimal("40"))
                self.assertEqual(price_change_list[1]["price_change"], Decimal("25"))
                self.assertEqual(
                    price_change_list[1]["price_change_vat"], Decimal("4.8387")
                )
                self.assertEqual(price_change_list[1]["month_count"], 6)
                self.assertEqual(
                    price_change_list[1]["start_date"], date(CURRENT_YEAR, 7, 1)
                )
                self.assertEqual(
                    price_change_list[1]["end_date"], date(CURRENT_YEAR, 12, 31)
                )


class TestParkingPermit(TestCase):
    def setUp(self):
        self.permit = ParkingPermitFactory()

    def test_should_have_is_order_confirmed_property_False(self):
        assert self.permit.is_order_confirmed is False

    def test_should_have_is_order_confirmed_property_True(self):
        order = OrderFactory(status=OrderStatus.CONFIRMED)
        order.permits.add(self.permit)
        assert self.permit.is_order_confirmed is True

    def test_should_return_correct_product_name(self):
        self.assertIsNotNone(self.permit.parking_zone.name)

    def test_checkout_url_if_latest_order_none(self):
        self.assertIsNone(self.permit.checkout_url)

    def test_checkout_url_if_latest_order_not_none(self):
        item = OrderItemFactory(permit=self.permit)
        self.permit.orders.add(item.order)
        self.assertEqual(self.permit.checkout_url, item.order.talpa_checkout_url)

    def test_checkout_url_if_latest_order_and_pending_request(self):
        ext_request = ParkingPermitExtensionRequestFactory(permit=self.permit)
        item = OrderItemFactory(permit=self.permit)
        self.permit.orders.add(item.order)
        self.assertEqual(self.permit.checkout_url, ext_request.order.talpa_checkout_url)

    def test_can_be_refunded_fixed(self):
        permit = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.VALID,
        )

        self.assertTrue(permit.can_be_refunded)

    def test_can_be_refunded_fixed_inactive(self):
        permit = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.CLOSED,
        )

        self.assertFalse(permit.can_be_refunded)

    @freeze_time(timezone.make_aware(datetime(2024, 1, 1)))
    def test_can_be_refunded_open_ended_already_started(self):
        permit = ParkingPermitFactory(
            contract_type=ContractType.OPEN_ENDED,
            status=ParkingPermitStatus.VALID,
            start_time=timezone.now() - timedelta(days=1),
            end_time=timezone.now() + timedelta(days=30),
        )

        self.assertFalse(permit.can_be_refunded)

    @freeze_time(timezone.make_aware(datetime(2024, 1, 1)))
    def test_can_be_refunded_open_ended_ends_more_than_month(self):
        permit = ParkingPermitFactory(
            contract_type=ContractType.OPEN_ENDED,
            status=ParkingPermitStatus.VALID,
            start_time=timezone.now() - timedelta(days=1),
            end_time=timezone.now() + timedelta(days=59),
        )

        self.assertTrue(permit.can_be_refunded)

    @override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=False)
    @patch("requests.post", return_value=MockResponse(201))
    def test_should_save_talpa_product_id_when_creating_talpa_product_successfully(
        self, mock_post
    ):
        self.permit.create_parkkihubi_permit()
        mock_post.assert_called_once()
        self.assertEqual(mock_post.return_value.status_code, 201)

    @override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=False)
    @patch("requests.post", return_value=MockResponse(400))
    def test_should_raise_error_when_creating_talpa_product_failed(self, mock_post):
        self.permit.vehicle.registration_number = ""
        with self.assertRaises(ParkkihubiPermitError):
            self.permit.create_parkkihubi_permit()
            mock_post.assert_called_once()
            self.assertEqual(mock_post.return_value.status_code, 400)

    @freeze_time("2024-02-05")
    def test_get_price_list_for_extended_permit(self):
        now = timezone.now()

        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=now - timedelta(days=23),
            end_time=now + timedelta(days=7),
            month_count=1,
        )

        ProductFactory(
            zone=permit.parking_zone,
            type=ProductType.RESIDENT,
            start_date=(now - timedelta(days=360)).date(),
            end_date=(now + timedelta(days=60)).date(),
            unit_price=Decimal("30.00"),
        )

        ProductFactory(
            zone=permit.parking_zone,
            type=ProductType.RESIDENT,
            start_date=(now - timedelta(days=61)).date(),
            end_date=(now + timedelta(days=365)).date(),
            unit_price=Decimal("40.00"),
        )

        price_list = list(permit.get_price_list_for_extended_permit(3))

        self.assertEqual(len(price_list), 2)

        # 2x first product
        self.assertEqual(price_list[0]["start_date"], date(2024, 2, 13))
        self.assertEqual(price_list[0]["end_date"], date(2024, 4, 12))
        self.assertEqual(price_list[0]["month_count"], 2)
        self.assertEqual(price_list[0]["price"], Decimal("60.00"))
        self.assertEqual(price_list[0]["unit_price"], Decimal("30.00"))
        self.assertEqual(price_list[0]["net_price"], "48.39")
        self.assertEqual(price_list[0]["vat_price"], "11.61")

        # 1x second product
        self.assertEqual(price_list[1]["start_date"], date(2024, 4, 13))
        self.assertEqual(price_list[1]["end_date"], date(2024, 5, 12))
        self.assertEqual(price_list[1]["month_count"], 1)
        self.assertEqual(price_list[1]["price"], Decimal("40.00"))
        self.assertEqual(price_list[1]["unit_price"], Decimal("40.00"))
        self.assertEqual(price_list[1]["net_price"], "32.26")
        self.assertEqual(price_list[1]["vat_price"], "7.74")

    def test_max_extension_month_count_for_primary_vehicle(self):
        permit = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            primary_vehicle=True,
        )
        self.assertEqual(permit.max_extension_month_count, 12)

    def test_max_extension_month_count_for_secondary_vehicle(self):
        now = timezone.now()
        primary = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            primary_vehicle=True,
            status=ParkingPermitStatus.VALID,
            end_time=now + relativedelta(months=4, days=-1),
        )
        secondary = ParkingPermitFactory(
            customer=primary.customer,
            primary_vehicle=False,
            end_time=now + relativedelta(months=1, days=-1),
        )
        self.assertEqual(secondary.max_extension_month_count, 2)

    def test_max_extension_month_count_for_secondary_vehicle_zero(self):
        now = timezone.now()
        primary = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            primary_vehicle=True,
            status=ParkingPermitStatus.VALID,
            end_time=now + relativedelta(months=1, days=-1),
        )
        secondary = ParkingPermitFactory(
            customer=primary.customer,
            primary_vehicle=False,
            end_time=now + relativedelta(months=1, days=-1),
        )
        self.assertEqual(secondary.max_extension_month_count, 0)

    def test_max_extension_month_count_for_secondary_vehicle_one_month(self):
        now = timezone.now()
        start_time = now - relativedelta(days=3)
        primary = ParkingPermitFactory(
            contract_type=ContractType.FIXED_PERIOD,
            primary_vehicle=True,
            status=ParkingPermitStatus.VALID,
            start_time=start_time,
            end_time=start_time + relativedelta(months=3, days=-1),
        )
        secondary = ParkingPermitFactory(
            customer=primary.customer,
            primary_vehicle=False,
            end_time=now + relativedelta(months=1, days=-1),
        )
        self.assertEqual(secondary.max_extension_month_count, 1)

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_extend_permit_not_valid(self):
        self.assertFalse(
            ParkingPermitFactory(
                status=ParkingPermitStatus.CLOSED,
                contract_type=ContractType.FIXED_PERIOD,
                end_time=timezone.now() + timedelta(days=9),
            ).can_extend_permit,
        )

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_extend_permit_open_ended(self):
        self.assertFalse(
            ParkingPermitFactory(
                status=ParkingPermitStatus.VALID,
                contract_type=ContractType.OPEN_ENDED,
                end_time=timezone.now() + timedelta(days=9),
            ).can_extend_permit,
        )

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_extend_permit_end_date_none(self):
        self.assertFalse(
            ParkingPermitFactory(
                status=ParkingPermitStatus.VALID,
                contract_type=ContractType.FIXED_PERIOD,
                end_time=None,
            ).can_extend_permit,
        )

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_extend_permit_end_date_too_late(self):
        self.assertFalse(
            ParkingPermitFactory(
                status=ParkingPermitStatus.VALID,
                contract_type=ContractType.FIXED_PERIOD,
                end_time=timezone.now() + timedelta(days=30),
            ).can_extend_permit,
        )

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_extend_permit_existing_pending_request(self):
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
            end_time=timezone.now() + timedelta(days=9),
        )
        ParkingPermitExtensionRequestFactory(permit=permit)

        self.assertFalse(permit.can_extend_permit)

    @override_settings(PERMIT_EXTENSIONS_ENABLED=False)
    def test_can_extend_permit_feature_disabled(self):
        self.assertFalse(
            ParkingPermitFactory(
                status=ParkingPermitStatus.VALID,
                contract_type=ContractType.FIXED_PERIOD,
                end_time=timezone.now() + timedelta(days=9),
            ).can_extend_permit,
        )

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_extend_permit_no_other_requests(self):
        self.assertTrue(
            ParkingPermitFactory(
                status=ParkingPermitStatus.VALID,
                contract_type=ContractType.FIXED_PERIOD,
                end_time=timezone.now() + timedelta(days=9),
            ).can_extend_permit,
        )

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_extend_permit_existing_other_request(self):
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
            end_time=timezone.now() + timedelta(days=9),
        )
        ParkingPermitExtensionRequestFactory(
            permit=permit, status=ParkingPermitExtensionRequest.Status.APPROVED
        )

        self.assertTrue(permit.can_extend_permit)

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_admin_extend_permit_not_valid(self):
        self.assertFalse(
            ParkingPermitFactory(
                status=ParkingPermitStatus.CLOSED,
                contract_type=ContractType.FIXED_PERIOD,
                end_time=timezone.now() + timedelta(days=9),
            ).can_admin_extend_permit,
        )

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_admin_extend_permit_open_ended(self):
        self.assertFalse(
            ParkingPermitFactory(
                status=ParkingPermitStatus.VALID,
                contract_type=ContractType.OPEN_ENDED,
                end_time=timezone.now() + timedelta(days=9),
            ).can_admin_extend_permit,
        )

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_admin_extend_permit_end_date_none(self):
        self.assertFalse(
            ParkingPermitFactory(
                status=ParkingPermitStatus.VALID,
                contract_type=ContractType.FIXED_PERIOD,
                end_time=None,
            ).can_admin_extend_permit,
        )

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_admin_extend_permit_end_date_too_late(self):
        self.assertTrue(
            ParkingPermitFactory(
                status=ParkingPermitStatus.VALID,
                contract_type=ContractType.FIXED_PERIOD,
                end_time=timezone.now() + timedelta(days=30),
            ).can_admin_extend_permit,
        )

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_can_admin_extend_permit_existing_pending_request(self):
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
            end_time=timezone.now() + timedelta(days=9),
        )
        ParkingPermitExtensionRequestFactory(permit=permit)

        self.assertFalse(permit.can_admin_extend_permit)

    @override_settings(PERMIT_EXTENSIONS_ENABLED=False)
    def test_can_admin_extend_permit_feature_disabled(self):
        self.assertFalse(
            ParkingPermitFactory(
                status=ParkingPermitStatus.VALID,
                contract_type=ContractType.FIXED_PERIOD,
                end_time=timezone.now() + timedelta(days=9),
            ).can_admin_extend_permit,
        )

    @freeze_time("2024-3-4")
    @override_settings(PERMIT_EXTENSIONS_ENABLED=True, DEBUG_SKIP_PARKKIHUBI_SYNC=False)
    @patch("requests.patch", return_value=MockResponse(200))
    @patch("requests.post", return_value=MockResponse(201))
    def test_extend_permit(self, mock_post, mock_patch):
        now = timezone.now()
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=now,
            end_time=now + timedelta(days=30),
            month_count=1,
        )

        permit.extend_permit(3)

        mock_patch.assert_called_once()
        mock_post.assert_not_called()

        permit.refresh_from_db()

        self.assertEqual(permit.month_count, 4)
        self.assertEqual(permit.end_time.date(), date(2024, 7, 3))

    @freeze_time("2024-3-4")
    @override_settings(PERMIT_EXTENSIONS_ENABLED=True, DEBUG_SKIP_PARKKIHUBI_SYNC=False)
    @patch("requests.patch", return_value=MockResponse(404))
    @patch("requests.post", return_value=MockResponse(201))
    def test_extend_permit_create_new_parkkihubi_permit(self, mock_post, mock_patch):
        now = timezone.now()
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=now,
            end_time=now + timedelta(days=30),
            month_count=1,
        )

        permit.extend_permit(3)

        mock_patch.assert_called_once()
        mock_post.assert_called_once()

        permit.refresh_from_db()

        self.assertEqual(permit.month_count, 4)
        self.assertEqual(permit.end_time.date(), date(2024, 7, 3))
