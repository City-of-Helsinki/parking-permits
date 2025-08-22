import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.expressions import RawSQL

from audit_logger.models import AuditLog
from parking_permits.admin_resolvers import update_or_create_customer

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Command(BaseCommand):
    help = "Usage: python manage.py fix_broken_audit_entries"

    @transaction.atomic
    def handle(self, *args, **options):
        log_entries = (
            AuditLog.objects.annotate(
                field_type=RawSQL("jsonb_typeof(message->%s)", ("target",))
            )
            .filter(is_sent=False, field_type="object")
            .select_for_update()
        )

        num_entries = log_entries.count()
        logger.warning("Trying to fix %d invalid entries", num_entries)

        for log_entry in log_entries:
            message: dict = log_entry.message
            person_info = message.get("target", None)

            if person_info:
                try:
                    customer = update_or_create_customer(person_info, True)
                    message["target"] = customer
                    log_entry.save(update_fields=["message"])
                    logger.warning("Fixed entry id %d", log_entry.id)
                except Exception:
                    logger.exception("Failed to fix entry id %d", log_entry.id)
