import logging

from django.db import models
from django.utils.translation import gettext_lazy as _

from audit_logger.data import AuditMessageEncoder

LOG_LEVELS = (
    (logging.NOTSET, _("NotSet")),
    (logging.INFO, _("Info")),
    (logging.WARNING, _("Warning")),
    (logging.DEBUG, _("Debug")),
    (logging.ERROR, _("Error")),
    (logging.FATAL, _("Fatal")),
)


class AuditLog(models.Model):
    logger_name = models.CharField(max_length=100, verbose_name=_("Logger name"))
    level = models.PositiveSmallIntegerField(
        choices=LOG_LEVELS,
        default=logging.ERROR,
        db_index=True,
        verbose_name=_("Logging level"),
    )
    is_sent = models.BooleanField(default=False, verbose_name=_("Is sent"))
    message = models.JSONField(verbose_name=_("Message"), encoder=AuditMessageEncoder)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    trace = models.TextField(blank=True, null=True)

    def __str__(self):
        return AuditMessageEncoder().encode(self.message)

    class Meta:
        ordering = ("-created_at",)
        verbose_name_plural = verbose_name = "Audit logging"
