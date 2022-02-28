from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from parking_permits.constants import ParkingPermitEndType
from parking_permits.exceptions import (
    InvalidContractType,
    ParkkihubiPermitError,
    PermitCanNotBeEnded,
    ProductCatalogError,
)
from parking_permits.models import Order
from parking_permits.models.order import OrderStatus
from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus
from parking_permits.models.product import ProductType
from parking_permits.tests.factories import ParkingZoneFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import VehicleFactory
from parking_permits.tests.models.test_product import MockResponse
from parking_permits.utils import get_end_time


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
        secondary_start_time = timezone.make_aware(datetime(2022, 1, 1))
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

    def test_get_unused_order_items_raise_error_for_open_ended_permit(self):
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
        self.assertRaises(InvalidContractType, permit.get_unused_order_items)

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
        low_emission_vehicle = VehicleFactory(low_emission_vehicle=True)

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
            price_change_list = permit.get_price_change_list(
                low_emission_vehicle, self.zone_b
            )
            self.assertEqual(len(price_change_list), 2)
            self.assertEqual(price_change_list[0]["product"], "Pysäköintialue B")
            self.assertEqual(price_change_list[0]["previous_price"], Decimal("20"))
            self.assertEqual(price_change_list[0]["new_price"], Decimal("15"))
            self.assertEqual(price_change_list[0]["price_change"], Decimal("-5"))
            self.assertEqual(price_change_list[0]["price_change_vat"], Decimal("-1.2"))
            self.assertEqual(price_change_list[0]["month_count"], 2)
            self.assertEqual(price_change_list[0]["start_date"], date(2021, 5, 1))
            self.assertEqual(price_change_list[0]["end_date"], date(2021, 6, 30))
            self.assertEqual(price_change_list[1]["product"], "Pysäköintialue B")
            self.assertEqual(price_change_list[1]["previous_price"], Decimal("30"))
            self.assertEqual(price_change_list[1]["new_price"], Decimal("20"))
            self.assertEqual(price_change_list[1]["price_change"], Decimal("-10"))
            self.assertEqual(price_change_list[1]["price_change_vat"], Decimal("-2.4"))
            self.assertEqual(price_change_list[1]["month_count"], 6)
            self.assertEqual(price_change_list[1]["start_date"], date(2021, 7, 1))
            self.assertEqual(price_change_list[1]["end_date"], date(2021, 12, 31))

    def test_parking_permit_change_price_list_when_prices_go_up(self):
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
        low_emission_vehicle = VehicleFactory(low_emission_vehicle=True)

        start_time = timezone.make_aware(datetime(2021, 1, 1))
        end_time = get_end_time(start_time, 12)
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
        with freeze_time(datetime(2021, 4, 15)):
            price_change_list = permit.get_price_change_list(
                high_emission_vehicle, self.zone_b
            )
            self.assertEqual(len(price_change_list), 2)
            self.assertEqual(price_change_list[0]["product"], "Pysäköintialue B")
            self.assertEqual(price_change_list[0]["previous_price"], Decimal("10"))
            self.assertEqual(price_change_list[0]["new_price"], Decimal("30"))
            self.assertEqual(price_change_list[0]["price_change"], Decimal("20"))
            self.assertEqual(price_change_list[0]["price_change_vat"], Decimal("4.8"))
            self.assertEqual(price_change_list[0]["month_count"], 2)
            self.assertEqual(price_change_list[0]["start_date"], date(2021, 5, 1))
            self.assertEqual(price_change_list[0]["end_date"], date(2021, 6, 30))
            self.assertEqual(price_change_list[1]["product"], "Pysäköintialue B")
            self.assertEqual(price_change_list[1]["previous_price"], Decimal("15"))
            self.assertEqual(price_change_list[1]["new_price"], Decimal("40"))
            self.assertEqual(price_change_list[1]["price_change"], Decimal("25"))
            self.assertEqual(price_change_list[1]["price_change_vat"], Decimal("6"))
            self.assertEqual(price_change_list[1]["month_count"], 6)
            self.assertEqual(price_change_list[1]["start_date"], date(2021, 7, 1))
            self.assertEqual(price_change_list[1]["end_date"], date(2021, 12, 31))


class TestParkingPermit(TestCase):
    def setUp(self):
        self.permit = ParkingPermitFactory()

    def test_should_return_correct_product_name(self):
        self.assertIsNotNone(self.permit.parking_zone.name)

    @patch("requests.post", return_value=MockResponse(201))
    def test_should_save_talpa_product_id_when_creating_talpa_product_successfully(
        self, mock_post
    ):
        self.permit.create_parkkihubi_permit()
        mock_post.assert_called_once()
        self.assertEqual(mock_post.return_value.status_code, 201)

    @patch("requests.post", return_value=MockResponse(400))
    def test_should_raise_error_when_creating_talpa_product_failed(self, mock_post):
        self.permit.vehicle.registration_number = ""
        with self.assertRaises(ParkkihubiPermitError):
            self.permit.create_parkkihubi_permit()
            mock_post.assert_called_once()
            self.assertEqual(mock_post.return_value.status_code, 400)
