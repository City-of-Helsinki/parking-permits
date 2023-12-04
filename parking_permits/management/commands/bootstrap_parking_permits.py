from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Usage: python manage.py bootstrap_parking_permits"

    def handle(self, *args, **options):
        call_command("import_parking_zones")
        call_command("create_test_address")
        call_command(
            "create_parking_zone_products",
            start_date="2023-12-01",
            end_date="2026-12-31",
            price_increment_factor_old_zone=2.0,
            price_increment_factor_new_zone=3.0,
            low_emission_discount_old_zone=0.25,
            low_emission_discount_new_zone=0.1666,
        )
        call_command(
            "create_low_emission_criteria",
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        call_command(
            "create_low_emission_criteria",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )
        call_command(
            "create_low_emission_criteria",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )
        call_command(
            "create_low_emission_criteria",
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        call_command("create_group_mapping")
