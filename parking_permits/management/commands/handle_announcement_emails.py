from django.core.management.base import BaseCommand

from parking_permits.cron import handle_announcement_emails


class Command(BaseCommand):
    help = "Handle unhandled announcement emails."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Handling announcement emails."))
        handle_announcement_emails()
        self.stdout.write(self.style.SUCCESS("Handled all announcement emails."))
