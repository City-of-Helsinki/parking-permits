from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone

from parking_permits.models import ParkingPermit
from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus


class Command(BaseCommand):
    """
    Note: this command is run to correct errant open ended permit dates
    where an extra hour has been assigned due to DST (winter->summer) time changes.
    """

    help = "Fix DST end dates on open-ended permits."

    def handle(self, *args, **kwargs):
        # Ensure correct timezone
        with timezone.override("Europe/Helsinki"):
            permits = ParkingPermit.objects.filter(
                status=ParkingPermitStatus.VALID,
                contract_type=ContractType.OPEN_ENDED,
                end_time__hour=0,
                end_time__minute=59,
            )
            num_permits = permits.update(end_time=F("end_time") - timedelta(hours=1))

        self.stdout.write(self.style.SUCCESS(f"{num_permits} permit(s) updated"))
