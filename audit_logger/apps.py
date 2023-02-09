from django.apps import AppConfig


class AuditLoggerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit_logger"
    verbose_name = "Audit logging"
