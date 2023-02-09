from django.core.management.base import BaseCommand

from parking_permits.cron import automatic_expiration_remind_notification_of_permits


class Command(BaseCommand):
    help = "Remind user about permit expiration with notification (email)."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Reminding of permit expiration started...")
        )
        automatic_expiration_remind_notification_of_permits()
        self.stdout.write(self.style.SUCCESS("Reminding of permit expiration done."))
