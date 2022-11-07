from datetime import date, datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from parking_permits.models.vehicle import EmissionType, LowEmissionCriteria

LOW_EMISSION_CRITERIA = {
    EmissionType.NEDC: 37,
    EmissionType.WLTP: 50,
}


class Command(BaseCommand):
    help = "Create test low emission criteria"

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=datetime.now().year)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stdout.write("Cannot create test data in production environment")
            return

        start_date = date(options["year"], 1, 1)
        end_date = date(options["year"], 12, 31)
        LowEmissionCriteria.objects.get_or_create(
            start_date=start_date,
            end_date=end_date,
            defaults={
                "nedc_max_emission_limit": LOW_EMISSION_CRITERIA.get(EmissionType.NEDC),
                "wltp_max_emission_limit": LOW_EMISSION_CRITERIA.get(EmissionType.WLTP),
                "euro_min_class_limit": 6,
            },
        )

        self.stdout.write("Test LowEmissionCriteria created")
