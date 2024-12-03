from django.core.management.base import BaseCommand
from django.db import transaction

from parking_permits.models.vehicle import Vehicle


class Command(BaseCommand):
    help = "Change consent_low_emission_accepted to False for non-electric vehicles"

    def add_arguments(self, parser):
        parser.add_argument("--dry_run", type=bool, default=False)

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        vehicles = Vehicle.objects.filter(
            consent_low_emission_accepted=True
        ).select_related("power_type")
        i = 0
        for vehicle in vehicles:
            if not vehicle.power_type.is_electric():
                vehicle.consent_low_emission_accepted = False
                if not dry_run:
                    vehicle.save()
                i = i + 1

        if dry_run:
            self.stdout.write("This is a dry run!")
            self.stdout.write(
                f"Real run would change {i} vehicles to consent_low_emission_accepted=False"
            )
        else:
            self.stdout.write(
                f"Changed {i} vehicles to consent_low_emission_accepted=False"
            )
