from django.core.management.base import BaseCommand

from parking_permits.models import Order, ParkingPermit, ParkingPermitExtensionRequest


class Command(BaseCommand):
    help = "Populate orders with missing vehicles and permits with such data"

    def add_arguments(self, parser):
        parser.add_argument("--dry_run", type=bool, default=False)

    def handle(self, *args, **options):
        orders = Order.objects.filter(vehicles=[], permits=None)

        if options["dry_run"]:
            self.stdout.write(
                f"This action populates {orders.count()} orders with vehicle and permit data."
            )
            return

        for order in orders:
            extension_request = ParkingPermitExtensionRequest.objects.filter(
                order_id=order.id
            ).first()

            if not extension_request:
                continue

            parking_permit = ParkingPermit.objects.filter(
                id=extension_request.permit_id
            ).first()

            if not parking_permit or not parking_permit.vehicle:
                continue

            order.vehicles = [parking_permit.vehicle.registration_number]
            order.save()

            order.permits.add(parking_permit)

            self.stdout.write(
                f"Order {order.id}: added permit {parking_permit.id} and vehicle "
                f"{parking_permit.vehicle.registration_number}."
            )
