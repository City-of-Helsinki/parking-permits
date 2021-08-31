import logging
from datetime import date
from importlib import import_module

from django.core.management.base import BaseCommand
from django.db import transaction

from parking_permits_app.constants import EmissionType
from parking_permits_app.models import LowEmissionCriteria, VehicleType

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Usage: python manage.py create_low_emission_criteria --year 2021 --data-module parking_permits_app.data.2021"  # noqa

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--data-module", type=str, required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        data_module = import_module(options.get("data_module"))

        for (
            vehicle_type,
            emission_criteria,
        ) in data_module.LOW_EMISSION_CRITERIA.items():
            obj, created = LowEmissionCriteria.objects.get_or_create(
                vehicle_type=VehicleType.objects.get(type=vehicle_type),
                nedc_max_emission_limit=emission_criteria.get(EmissionType.NEDC.value),
                wltp_max_emission_limit=emission_criteria.get(EmissionType.WLTP.value),
                euro_min_class_limit=emission_criteria.get(EmissionType.EURO.value),
                start_date=date(day=1, month=1, year=options.get("year")),
                end_date=date(day=31, month=12, year=options.get("year")),
            )

            if created:
                logger.info(f"{obj.vehicle_type.type} emission criteria created")
            else:
                logger.info(f"{obj.vehicle_type.type} emission criteria already exists")
