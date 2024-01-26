from decimal import Decimal

import pytest
from django.test import TestCase

from parking_permits.talpa.order import TalpaOrderManager
from parking_permits.tests.factories.order import OrderItemFactory


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

        data = TalpaOrderManager._create_order_data(order_item.order)
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

        data = TalpaOrderManager._create_item_data(order_item.order, order_item)

        self.assertEqual(data["priceNet"], "24.19")
        self.assertEqual(data["priceVat"], "5.81")
        self.assertEqual(data["priceGross"], "30.00")
        self.assertEqual(data["vatPercentage"], "24")

        self.assertEqual(data["rowPriceNet"], "48.39")
        self.assertEqual(data["rowPriceVat"], "11.61")
        self.assertEqual(data["rowPriceTotal"], "60.00")


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
