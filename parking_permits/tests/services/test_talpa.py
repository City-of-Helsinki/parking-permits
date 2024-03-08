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
        pytest.param(30, "30.00", "24.19", "5.81", id="gross: 30"),
        pytest.param(30.50, "30.50", "24.60", "5.90", id="gross: 30.50"),
        pytest.param(60, "60.00", "48.39", "11.61", id="gross: 60"),
        pytest.param(100, "100.00", "80.64", "19.36", id="gross: 100"),
        pytest.param(120, "120.00", "96.77", "23.23", id="gross: 120"),
        pytest.param(720.01, "720.01", "580.65", "139.36", id="gross: 720.01"),
    ],
)
def test_pricing(value, gross, net, vat):
    pricing = Pricing.calculate(value, 0.24)

    assert pricing.net + pricing.vat == pricing.gross

    assert pricing.format_gross() == gross
    assert pricing.format_net() == net
    assert pricing.format_vat() == vat


def test_add_pricing():
    total_pricing = Pricing()

    total_pricing += Pricing.calculate(60, 0.24)
    total_pricing += Pricing.calculate(120, 0.24)

    assert total_pricing.format_gross() == "180.00"
    assert total_pricing.format_net() == "145.16"
    assert total_pricing.format_vat() == "34.84"


class TestTalpaOrderManager(TestCase):
    def test_create_order_data(self):
        order_item = OrderItemFactory(
            unit_price=Decimal(30),
            payment_unit_price=Decimal(30),
            quantity=2,
            vat=Decimal(0.24),
        )

        OrderItemFactory(
            unit_price=Decimal(60),
            payment_unit_price=Decimal(60),
            quantity=3,
            order=order_item.order,
            vat=Decimal(0.24),
        )

        data = TalpaOrderManager.create_order_data(order_item.order)
        self.assertEqual(data["priceNet"], "193.55")
        self.assertEqual(data["priceVat"], "46.45")
        self.assertEqual(data["priceTotal"], "240.00")

    def test_create_item_data(self):
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
        self.assertEqual(data["vatPercentage"], "24")

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
