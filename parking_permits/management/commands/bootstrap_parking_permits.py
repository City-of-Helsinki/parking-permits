from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Usage: python manage.py bootstrap_parking_permits"

    def handle(self, *args, **options):
        call_command("create_test_address")
        call_command("import_parking_zones")
        call_command(
            "create_parking_zone_products",
            year=2021,
        )
        call_command(
            "create_parking_zone_products",
            year=2022,
        )
        call_command(
            "create_parking_zone_products",
            year=2023,
        )
        call_command(
            "create_low_emission_criteria",
            year=2021,
        )
        call_command(
            "create_low_emission_criteria",
            year=2022,
        )
        call_command(
            "create_low_emission_criteria",
            year=2023,
        )
        call_command("create_group_mapping")
