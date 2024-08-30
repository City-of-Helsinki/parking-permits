from decimal import Decimal

from django.test import TestCase

from parking_permits.tests.factories.refund import RefundFactory


class TestRefund(TestCase):
    def test_vat_zero_amount(self):
        refund = RefundFactory(amount=0)
        assert refund.vat_amount == Decimal(0)

    def test_vat(self):
        refund = RefundFactory(amount=100, vat=Decimal(0.255))
        self.assertAlmostEqual(refund.vat_amount, Decimal(20.32), delta=Decimal("0.01"))

    def test_prev_vat(self):
        refund = RefundFactory(amount=100, vat=Decimal(0.24))
        self.assertAlmostEqual(refund.vat_amount, Decimal(19.35), delta=Decimal("0.01"))
