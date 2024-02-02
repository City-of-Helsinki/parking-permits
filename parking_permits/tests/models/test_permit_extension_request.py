from django.test import TestCase

from parking_permits.models import ParkingPermitExtensionRequest
from parking_permits.tests.factories.permit_extension_request import (
    ParkingPermitExtensionRequestFactory,
)


class TestPermitExtensionRequest(TestCase):
    def setUp(self):
        self.ext_request = ParkingPermitExtensionRequestFactory(month_count=3)

    def test_is_pending(self):
        self.assertTrue(self.ext_request.is_pending())
        self.assertTrue(ParkingPermitExtensionRequest.objects.pending().exists())

    def test_approve(self):
        self.ext_request.approve()
        self.assertTrue(self.ext_request.is_approved())
        self.assertEqual(self.ext_request.permit.month_count, 4)
        self.assertFalse(ParkingPermitExtensionRequest.objects.pending().exists())

    def test_reject(self):
        self.ext_request.reject()
        self.assertTrue(self.ext_request.is_rejected())
        self.assertEqual(self.ext_request.permit.month_count, 1)
        self.assertFalse(ParkingPermitExtensionRequest.objects.pending().exists())
