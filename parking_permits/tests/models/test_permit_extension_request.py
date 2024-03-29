from django.test import TestCase

from parking_permits.models import ParkingPermitExtensionRequest
from parking_permits.tests.factories.permit_extension_request import (
    ParkingPermitExtensionRequestFactory,
)


class TestPermitExtensionRequest(TestCase):
    def setUp(self):
        self.ext_request = ParkingPermitExtensionRequestFactory(month_count=3)

    def test_pending(self):
        ParkingPermitExtensionRequestFactory(
            status=ParkingPermitExtensionRequest.Status.APPROVED
        )
        assert ParkingPermitExtensionRequest.objects.pending().count() == 1

    def test_cancel_pending(self):
        approved = ParkingPermitExtensionRequestFactory(
            status=ParkingPermitExtensionRequest.Status.APPROVED
        )
        ParkingPermitExtensionRequest.objects.cancel_pending()

        self.ext_request.refresh_from_db()

        self.assertTrue(self.ext_request.is_cancelled())

        approved.refresh_from_db()
        self.assertFalse(approved.is_cancelled())

    def test_is_pending(self):
        self.assertTrue(self.ext_request.is_pending())
        self.assertTrue(ParkingPermitExtensionRequest.objects.pending().exists())

    def test_approve(self):
        self.ext_request.approve()
        self.assertTrue(self.ext_request.is_approved())
        self.assertEqual(self.ext_request.permit.month_count, 4)
        self.assertFalse(ParkingPermitExtensionRequest.objects.pending().exists())

    def test_cancel(self):
        self.ext_request.cancel()
        self.assertTrue(self.ext_request.is_cancelled())
        self.assertFalse(ParkingPermitExtensionRequest.objects.pending().exists())
