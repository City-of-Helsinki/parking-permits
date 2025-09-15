import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.expressions import RawSQL

from audit_logger.models import AuditLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Usage: python manage.py fix_broken_audit_log_targets [--dry-run]"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse entries that would be fixed, without fixing them.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"] or False

        entries = (
            AuditLog.objects.annotate(
                target_type=RawSQL("jsonb_typeof(message->%s)", ["target"])
            )
            .filter(
                is_sent=False,
                target_type="object",
                message__message="User extended parking permit.",
            )
            .select_for_update()
        )

        num_entries = entries.count()
        entry_ids = list(entries.values_list("id", flat=True))
        modified_ids = ", ".join([str(entry_id) for entry_id in entry_ids])

        if num_entries == 0:
            logger.warning("No broken audit log entries found")
            return

        if dry_run:
            logger.warning("--- DRY RUN MODE ---")
            logger.warning("No data will be modified.")

            logger.warning(
                "Would modify %d user extended parking permit entries", num_entries
            )
            logger.warning(
                "Audit log entries with ids [%s] would be modified", modified_ids
            )
        else:
            logger.warning(
                "Modifying %d user extended parking permit entries", num_entries
            )

            for entry in entries:
                entry.message["target"] = entry.message["target"]["checkout_url"]
                entry.save()

            logger.warning("Modified audit log entries with ids [%s]", modified_ids)
