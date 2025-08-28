import logging
from django.db import transaction
from django.core.management.base import BaseCommand

from audit_logger.models import AuditLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Usage: python manage.py remove_broken_audit_log_entries"

    @transaction.atomic
    def handle(self, *args, **options):
        entries = AuditLog.objects.filter(
            is_sent=False, message__message="Admin retrieved customer details."
        ).select_for_update()

        num_entries = entries.count()
        if num_entries == 0:
            logger.warning("No broken audit log entries found")
            return

        logger.warning("Removing %d customer retrieve audit log entries", num_entries)

        entry_ids = list(entries.values_list("id", flat=True))
        removed_ids = ", ".join([str(entry_id) for entry_id in entry_ids])

        entries.delete()
        logger.warning("Removed audit log entries with ids [%s]", removed_ids)
