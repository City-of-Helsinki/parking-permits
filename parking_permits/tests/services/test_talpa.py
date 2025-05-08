from decimal import Decimal

import pytest
from django.test import TestCase

from parking_permits.talpa.order import TalpaOrderManager
from parking_permits.talpa.pricing import Pricing
from parking_permits.tests.factories.order import OrderItemFactory


@pytest.mark.parametrize(
    "value,gross,net,vat",
    [
        pytest.param(None, "0.00", "0.00", "0.00", id="gross: None"),
        pytest.param(0, "0.00", "0.00", "0.00", id="gross: 0"),
        pytest.param(30, "30.00", "23.90", "6.10", id="gross: 30"),
        pytest.param(30.50, "30.50", "24.30", "6.20", id="gross: 30.50"),
        pytest.param(48.40, "48.40", "38.57", "9.83", id="gross: 48.50"),
        pytest.param(60, "60.00", "47.81", "12.19", id="gross: 60"),
        pytest.param(100, "100.00", "79.68", "20.32", id="gross: 100"),
        pytest.param(120, "120.00", "95.62", "24.38", id="gross: 120"),
        pytest.param(720.01, "720.01", "573.71", "146.30", id="gross: 720.01"),
    ],
)
def test_pricing(value, gross, net, vat):
    pricing = Pricing.calculate(value, 0.255)

    assert pricing.net + pricing.vat == pricing.gross

    assert pricing.format_gross() == gross
    assert pricing.format_net() == net
    assert pricing.format_vat() == vat


def test_add_pricing():
    total_pricing = Pricing()

    total_pricing += Pricing.calculate(60, 0.255)
    total_pricing += Pricing.calculate(120, 0.255)

    assert total_pricing.format_gross() == "180.00"
    assert total_pricing.format_net() == "143.43"
    assert total_pricing.format_vat() == "36.57"


class TestTalpaOrderManager(TestCase):
    def test_create_order_data(self):
        order_item = OrderItemFactory(
            unit_price=Decimal(30),
            payment_unit_price=Decimal(30),
            quantity=2,
            vat=Decimal(0.255),
        )

        OrderItemFactory(
            unit_price=Decimal(60),
            payment_unit_price=Decimal(60),
            quantity=3,
            order=order_item.order,
            vat=Decimal(0.255),
        )

        data = TalpaOrderManager.create_order_data(order_item.order)
        self.assertEqual(data["priceTotal"], "240.00")
        self.assertEqual(data["priceNet"], "191.23")
        self.assertEqual(data["priceVat"], "48.77")

    def test_create_item_data(self):
        order_item = OrderItemFactory(
            unit_price=Decimal(60),
            payment_unit_price=Decimal(60),
            quantity=2,
            vat=Decimal(0.255),
        )

        data, pricing = TalpaOrderManager.create_item_data(order_item.order, order_item)

        self.assertEqual(data["priceNet"], "47.81")
        self.assertEqual(data["priceVat"], "12.19")
        self.assertEqual(data["priceGross"], "60.00")
        self.assertEqual(data["vatPercentage"], "25.50")

        self.assertEqual(data["rowPriceNet"], "95.62")
        self.assertEqual(data["rowPriceVat"], "24.38")
        self.assertEqual(data["rowPriceTotal"], "120.00")

        self.assertEqual(pricing.format_gross(), "120.00")
        self.assertEqual(pricing.format_net(), "95.62")
        self.assertEqual(pricing.format_vat(), "24.38")

    def test_create_item_data_prev_vat(self):
        order_item = OrderItemFactory(
            unit_price=Decimal(30),
            payment_unit_price=Decimal(30),
            quantity=2,
            vat=Decimal(0.24),
        )

        data, pricing = TalpaOrderManager.create_item_data(order_item.order, order_item)

        self.assertEqual(data["priceNet"], "24.19")
        self.assertEqual(data["priceVat"], "5.81")
        self.assertEqual(data["priceGross"], "30.00")
        self.assertEqual(data["vatPercentage"], "24.00")

        self.assertEqual(data["rowPriceNet"], "48.39")
        self.assertEqual(data["rowPriceVat"], "11.61")
        self.assertEqual(data["rowPriceTotal"], "60.00")

        self.assertEqual(pricing.format_gross(), "60.00")
        self.assertEqual(pricing.format_net(), "48.39")
        self.assertEqual(pricing.format_vat(), "11.61")


@pytest.mark.parametrize(
    "value, expected",
    [
        (1.0, "1"),
        (1.01, "1"),
        (1.499999, "1"),
        (1.5, "2"),
    ],
)
def test_round_int(value, expected):
    assert TalpaOrderManager.round_int(value) == expected
