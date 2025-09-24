from django.core.management.base import BaseCommand
from django.db import transaction

from parking_permits.models.order import Order, OrderStatus
from parking_permits.models.parking_permit import ParkingPermit, ParkingPermitStatus

CANCELLED = ParkingPermitStatus.CANCELLED
PAYMENT_IN_PROGRESS = ParkingPermitStatus.PAYMENT_IN_PROGRESS


class Command(BaseCommand):
    help = "Cancel permits and their latest orders for permits that"
    "have been stuck in PAYMENT_IN_PROGRESS-status for long enough."
    "(controlled by TALPA_ORDER_PAYMENT_WEBHOOK_WAIT_BUFFER_MINS-setting)"

    def handle(self, *args, **options):
        unpaid_permits = ParkingPermit.objects.filter(status=PAYMENT_IN_PROGRESS)

        permits_to_update = []
        orders_to_update = []

        for permit in unpaid_permits:
            if permit.has_timed_out_payment_in_progress:
                # NOTE: the existence of the latest order is already checked
                # by the has_timed_out_payment_in_progress-property
                latest_order = permit.latest_order
                # NOTE: permit extension orders do NOT set the permit into
                # PAYMENT_IN_PROGRESS-status, so there are no such permits
                # which would need to be "returned" to VALID-status.
                permit.status = CANCELLED
                permits_to_update.append(permit)

                latest_order.status = OrderStatus.CANCELLED
                orders_to_update.append(latest_order)

        with transaction.atomic():
            # NOTE: bulk_update() DOES NOT call save() internally,
            # but this is actually desirable here:
            # - the only custom logic in ParkingPermit.save() is used
            # to check for duplicate permits
            # - we are updating permits to CANCELLED-status, meaning that
            # it's impossible to break the constraint as duplicates are allowed
            # for permits with CANCELLED-status. We're better off
            # (performance-wise) skipping the check altogether.
            ParkingPermit.objects.bulk_update(
                objs=permits_to_update,
                fields=["status"],
                batch_size=200,
            )
            Order.objects.bulk_update(
                objs=orders_to_update,
                fields=["status"],
                batch_size=200,
            )
