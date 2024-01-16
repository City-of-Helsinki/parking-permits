from decimal import Decimal

from django.test import TestCase

from parking_permits.tests.factories.order import OrderFactory, OrderItemFactory
from parking_permits.tests.factories.refund import RefundFactory


class TestRefund(TestCase):
    def test_vat_no_order_items(self):
        refund = RefundFactory()
        assert refund.vat == Decimal(0)

    def test_vat_with_different_rates(self):
        order = OrderFactory()

        OrderItemFactory(unit_price=10, vat=0.24, order=order, quantity=2)
        OrderItemFactory(unit_price=10, vat=0.20, order=order, quantity=1)

        refund = RefundFactory(order=order, amount=200)

        self.assertAlmostEqual(refund.vat, Decimal(5.53), delta=Decimal("0.01"))
