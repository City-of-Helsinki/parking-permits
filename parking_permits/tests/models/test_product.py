import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import CreateTalpaProductError
from parking_permits.models import Product
from parking_permits.models.product import Accounting
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.zone import ParkingZoneFactory


class TestProductQuerySet(TestCase):
    def test_for_date_range_returns_products_overlaps_with_range(self):
        zone = ParkingZoneFactory(name="A")
        ProductFactory(
            zone=zone, start_date=date(2021, 1, 1), end_date=date(2021, 8, 31)
        )
        ProductFactory(
            zone=zone, start_date=date(2021, 9, 1), end_date=date(2021, 12, 31)
        )
        ProductFactory(
            zone=zone, start_date=date(2022, 1, 1), end_date=date(2022, 12, 31)
        )
        qs = Product.objects.for_date_range(date(2021, 6, 1), date(2022, 3, 30))
        self.assertEqual(qs.count(), 3)

    def test_for_date_range_returns_product_covers_full_range(self):
        zone = ParkingZoneFactory(name="A")
        ProductFactory(
            zone=zone, start_date=date(2021, 1, 1), end_date=date(2021, 12, 31)
        )
        ProductFactory(
            zone=zone, start_date=date(2022, 1, 1), end_date=date(2022, 12, 31)
        )
        qs = Product.objects.for_date_range(date(2022, 2, 1), date(2022, 8, 31))
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs[0].start_date, date(2022, 1, 1))


class MockResponse:
    reasons = {401: "Forbidden"}

    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self.reason = self.reasons.get(status_code)
        self.json_data = json_data
        self.text = "Error" if status_code != 200 else ""

    def json(self):
        return self.json_data


class TestProduct(TestCase):
    def setUp(self):
        zone = ParkingZoneFactory(name="A")
        self.product = ProductFactory(zone=zone)

    def test_should_return_correct_product_name(self):
        with translation.override("fi"):
            self.assertEqual(self.product.name, f"{_('Parking zone')} A")

    @patch(
        "requests.post",
        return_value=MockResponse(201, {"productId": uuid.uuid4()}),
    )
    def test_should_save_talpa_product_id_when_creating_talpa_product_successfully(
        self, mock_post
    ):
        self.product.create_talpa_product()
        mock_post.assert_called_once()
        self.assertIsNotNone(self.product.talpa_product_id)

    @patch("requests.post", return_value=MockResponse(401))
    def test_should_raise_error_when_creating_talpa_product_failed(self, mock_post):
        with self.assertRaises(CreateTalpaProductError):
            self.product.create_talpa_product()
            mock_post.assert_called_once()

    def test_get_modified_unit_price_return_modified_price(self):
        product = ProductFactory(
            unit_price=Decimal(10), low_emission_discount=Decimal(0.5)
        )
        low_emission_price = product.get_modified_unit_price(True, False)
        self.assertEqual(low_emission_price, Decimal(5))

        secondary_vehicle_price = product.get_modified_unit_price(False, True)
        self.assertEqual(secondary_vehicle_price, Decimal(15))

        secondary_vehicle_low_emission_price = product.get_modified_unit_price(
            True, True
        )
        self.assertEqual(secondary_vehicle_low_emission_price, Decimal(7.5))

    def test_get_talpa_pricing(self):
        product = ProductFactory(
            unit_price=Decimal(60),
            vat=0.255,
        )
        pricing = product.get_talpa_pricing(False, False)
        assert pricing == {
            "price_gross": "60.00",
            "price_net": "47.81",
            "price_vat": "12.19",
            "vat_percentage": "25.50",
        }

    def test_get_talpa_pricing_other_vat(self):
        product = ProductFactory(
            unit_price=Decimal(20),
            vat=0.24,
        )
        pricing = product.get_talpa_pricing(False, False)
        assert pricing == {
            "price_gross": "20.00",
            "price_net": "16.13",
            "price_vat": "3.87",
            "vat_percentage": "24.00",
        }

    def test_get_talpa_pricing_with_discount(self):
        product = ProductFactory(
            unit_price=Decimal(60),
            low_emission_discount=Decimal(0.25),
            vat=0.255,
        )
        pricing = product.get_talpa_pricing(True, False)
        assert pricing == {
            "price_gross": "45.00",
            "price_net": "35.86",
            "price_vat": "9.14",
            "vat_percentage": "25.50",
        }

    def test_get_talpa_pricing_with_secondary_vehicle(self):
        product = ProductFactory(
            unit_price=Decimal(60),
            low_emission_discount=Decimal(0.25),
            vat=0.255,
        )
        pricing = product.get_talpa_pricing(False, True)
        assert pricing == {
            "price_gross": "90.00",
            "price_net": "71.71",
            "price_vat": "18.29",
            "vat_percentage": "25.50",
        }

    def test_get_talpa_pricing_with_discount_secondary_vehicle(self):
        product = ProductFactory(
            unit_price=Decimal(60),
            low_emission_discount=Decimal(0.25),
            vat=0.255,
        )
        pricing = product.get_talpa_pricing(True, True)
        assert pricing == {
            "price_gross": "67.50",
            "price_net": "53.78",
            "price_vat": "13.72",
            "vat_percentage": "25.50",
        }

    def test_get_talpa_pricing_with_precise_discount(self):
        product = ProductFactory(
            unit_price=Decimal(64.50),
            low_emission_discount=Decimal(0.2496124031),
            vat=0.255,
        )
        pricing = product.get_talpa_pricing(True, False)
        assert pricing == {
            "price_gross": "48.40",
            "price_net": "38.57",
            "price_vat": "9.83",
            "vat_percentage": "25.50",
        }

    def test_get_talpa_pricing_with_precise_discount_secondary_vehicle(self):
        product = ProductFactory(
            unit_price=Decimal(64.50),
            low_emission_discount=Decimal(0.2496124031),
            vat=0.255,
        )
        pricing = product.get_talpa_pricing(True, True)
        assert pricing == {
            "price_gross": "72.60",
            "price_net": "57.85",
            "price_vat": "14.75",
            "vat_percentage": "25.50",
        }

    def test_get_talpa_pricing_with_discount_other_vat(self):
        product = ProductFactory(
            unit_price=Decimal(20),
            low_emission_discount=Decimal(0.5),
            vat=0.24,
        )
        pricing = product.get_talpa_pricing(True, False)
        assert pricing == {
            "price_gross": "10.00",
            "price_net": "8.06",
            "price_vat": "1.94",
            "vat_percentage": "24.00",
        }

    @patch(
        "requests.post",
        return_value=MockResponse(201),
    )
    def test_create_talpa_accounting(self, mock_post):
        self.product.talpa_product_id = uuid.uuid4()
        self.product.save()
        self.product.create_talpa_accounting()
        mock_post.assert_called_once()
        self.assertIsNotNone(self.product.accounting)

    @patch(
        "requests.post",
        return_value=MockResponse(201),
    )
    def test_create_talpa_accounting_without_product_id(self, mock_post):
        self.product.create_talpa_accounting()
        mock_post.assert_not_called()
        self.assertIsNone(self.product.accounting)

    @patch(
        "requests.post",
        return_value=MockResponse(201),
    )
    def test_update_talpa_accounting(self, mock_post):
        self.product.talpa_product_id = uuid.uuid4()
        company_code = "123"
        self.product.accounting = Accounting.objects.create(company_code=company_code)
        self.product.save()
        self.product.update_talpa_accounting()
        mock_post.assert_called_once()
        self.assertIsNotNone(self.product.accounting)
        self.assertEqual(self.product.accounting.company_code, company_code)

    @patch(
        "requests.post",
        return_value=MockResponse(201),
    )
    def test_update_talpa_accounting_without_product_id(self, mock_post):
        company_code = "123"
        self.product.accounting = Accounting.objects.create(company_code=company_code)
        self.product.save()
        self.product.update_talpa_accounting()
        mock_post.assert_not_called()

    @patch("requests.post", return_value=MockResponse(401))
    def test_should_raise_error_when_creating_talpa_accounting_failed(self, mock_post):
        with self.assertRaises(CreateTalpaProductError):
            self.product.talpa_product_id = uuid.uuid4()
            self.product.save()
            self.product.create_talpa_accounting()
            mock_post.assert_called_once()
