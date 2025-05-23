from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef
from django.utils import timezone

from parking_permits.models import (
    OrderItem,
    ParkingPermit,
    ParkingPermitExtensionRequest,
)
from parking_permits.models.parking_permit import ParkingPermitStatus


class Command(BaseCommand):
    help = "Remove/cancel draft permits and permit extension requests older than specified time."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=0)
        parser.add_argument("--minutes", type=int, default=30)
        parser.add_argument("--preliminary_hours", type=int, default=72)
        parser.add_argument("--preliminary_minutes", type=int, default=0)

    def handle(self, *args, **options):
        minutes = options["minutes"] + (60 * options["hours"])
        now = timezone.localtime()
        time_limit = now - timedelta(minutes=minutes)

        preliminary_minutes = options["preliminary_minutes"] + (
            60 * options["preliminary_hours"]
        )
        preliminary_time_limit = now - timedelta(minutes=preliminary_minutes)

        # Delete draft permits
        # NOTE: there should not be draft permits with orders, but exclude
        # these just in case.

        permits = ParkingPermit.objects.annotate(
            has_orders=Exists(OrderItem.objects.filter(permit=OuterRef("pk")))
        ).filter(
            has_orders=False,
            created_at__lt=time_limit,
            status=ParkingPermitStatus.DRAFT,
        )

        if num_permits := permits.count():
            permits.delete()
            self.stdout.write(f"{num_permits} draft permit(s) deleted")
        else:
            self.stdout.write("No draft permits deleted")

        # Delete preliminary permits
        # NOTE: there should not be preliminary permits with orders, but exclude
        # these just in case.

        preliminary_permits = ParkingPermit.objects.annotate(
            has_orders=Exists(OrderItem.objects.filter(permit=OuterRef("pk")))
        ).filter(
            has_orders=False,
            created_at__lt=preliminary_time_limit,
            status=ParkingPermitStatus.PRELIMINARY,
        )

        if num_preliminary_permits := preliminary_permits.count():
            preliminary_permits.delete()
            self.stdout.write(
                f"{num_preliminary_permits} preliminary permit(s) deleted"
            )
        else:
            self.stdout.write("No preliminary permits deleted")

        # Delete permit extension requests
        # These will all have FK to Order, so we don't want to delete them completely,
        # just mark as CANCELLED.

        ext_requests = ParkingPermitExtensionRequest.objects.filter(
            created_at__lt=time_limit,
            status=ParkingPermitExtensionRequest.Status.PENDING,
        )

        if num_ext_requests := ext_requests.count():
            ext_requests.update(
                status=ParkingPermitExtensionRequest.Status.CANCELLED,
                status_changed_at=now,
            )
            self.stdout.write(
                f"{num_ext_requests} pending permit extension request(s) cancelled"
            )
        else:
            self.stdout.write("No pending permit extension requests canceled")
