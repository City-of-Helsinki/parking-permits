import uuid
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from parking_permits.exceptions import CreateTalpaProductError
from parking_permits.models import Product
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
        self.assertEqual(self.product.name, "Pysäköintialue A")

    @patch("requests.post", return_value=MockResponse(201, {"productId": uuid.uuid4()}))
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
            self.assertIsNotNone(self.product.talpa_product_id)
