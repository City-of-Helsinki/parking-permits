from django.test import TestCase
from django.utils import timezone

from parking_permits.models.parking_permit import ParkingPermit, ParkingPermitStatus
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory

from ..cron import automatic_expiration_of_permits


class CronTestCase(TestCase):
    def setUp(self):
        self.customer = CustomerFactory(first_name="Firstname A", last_name="")
        ParkingPermitFactory(
            customer=self.customer,
            end_time=timezone.now() + timezone.timedelta(days=1),
            status=ParkingPermitStatus.VALID,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=timezone.now() + timezone.timedelta(days=-1),
            status=ParkingPermitStatus.DRAFT,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=timezone.now() + timezone.timedelta(days=1),
            status=ParkingPermitStatus.DRAFT,
        )
        ParkingPermitFactory(
            customer=self.customer,
            end_time=timezone.now() + timezone.timedelta(days=-1),
            status=ParkingPermitStatus.VALID,
        )

    def test_automatic_expiration_of_older_permits(self):
        valid_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.VALID)
        draft_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.DRAFT)
        self.assertEqual(valid_permits.count(), 2)
        self.assertEqual(draft_permits.count(), 2)

        automatic_expiration_of_permits()
        closed_permits = ParkingPermit.objects.filter(status=ParkingPermitStatus.CLOSED)
        self.assertEqual(valid_permits.count(), 1)
        self.assertEqual(draft_permits.count(), 2)
        self.assertEqual(closed_permits.count(), 1)
