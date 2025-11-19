from django.core.management.base import BaseCommand

from parking_permits.models.reporting import PermitCountSnapshot


class Command(BaseCommand):
    help = "Create daily permit count snapshots for the current date."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Creation of daily permit count snapshots started...")
        )
        PermitCountSnapshot.build_daily_snapshot()
        self.stdout.write(
            self.style.SUCCESS("Creation of daily permit count snapshots done.")
        )
