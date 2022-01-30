from django.utils import timezone

from parking_permits.models import ParkingPermit
from parking_permits.models.parking_permit import ParkingPermitStatus


def automatic_expiration_of_permits():
    ParkingPermit.objects.filter(
        end_time__lt=timezone.now(), status=ParkingPermitStatus.VALID
    ).update(status=ParkingPermitStatus.CLOSED)
