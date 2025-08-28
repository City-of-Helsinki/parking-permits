import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from audit_logger.models import AuditLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Usage: python manage.py remove_broken_audit_log_entries [--dry-run]"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse entries that would be deleted, without deleting them.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"] or False

        entries = AuditLog.objects.filter(
            is_sent=False, message__message="Admin retrieved customer details."
        ).select_for_update()

        num_entries = entries.count()
        entry_ids = list(entries.values_list("id", flat=True))
        removed_ids = ", ".join([str(entry_id) for entry_id in entry_ids])

        if num_entries == 0:
            logger.warning("No broken audit log entries found")
            return

        if dry_run:
            logger.warning("--- DRY RUN MODE ---")
            logger.warning("No data will be deleted.")

            logger.warning(
                "Would remove %d customer retrieve audit log entries", num_entries
            )
            logger.warning(
                "Audit log entries with ids [%s] would be removed", removed_ids
            )
        else:
            logger.warning(
                "Removing %d customer retrieve audit log entries", num_entries
            )
            entries.delete()
            logger.warning("Removed audit log entries with ids [%s]", removed_ids)
