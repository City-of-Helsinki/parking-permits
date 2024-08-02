from decimal import Decimal

from django.test import TestCase

from parking_permits.tests.factories.refund import RefundFactory


class TestRefund(TestCase):
    def test_vat_zero_amount(self):
        refund = RefundFactory(amount=0)
        assert refund.vat == Decimal(0)

    def test_vat(self):
        refund = RefundFactory(amount=100)
        self.assertAlmostEqual(refund.vat, Decimal(20.32), delta=Decimal("0.01"))
