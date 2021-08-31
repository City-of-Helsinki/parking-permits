import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from parking_permits_app import constants
from parking_permits_app.models import VehicleType

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Usage: python manage.py create_vehicle_types"

    @transaction.atomic
    def handle(self, *args, **options):
        for item in constants.VehicleType:
            vehicle_type, created = VehicleType.objects.get_or_create(type=item.value)

            if created:
                logger.info(f"{vehicle_type.type} vehicle type created")
            else:
                logger.info(f"{vehicle_type.type} vehicle type already exists")
