import logging

from django.db import models
from django.utils.text import camel_case_to_spaces

from audit_logger.enums import AuditLogLevel

_logging_level_to_audit_log_level = {
    logging.NOTSET: AuditLogLevel.TRACE,
    logging.DEBUG: AuditLogLevel.DEBUG,
    logging.INFO: AuditLogLevel.INFO,
    logging.WARNING: AuditLogLevel.ERROR,
    logging.ERROR: AuditLogLevel.ERROR,
    logging.FATAL: AuditLogLevel.ERROR,
}


def get_audit_log_level(logging_level: int) -> AuditLogLevel:
    return _logging_level_to_audit_log_level[logging_level]


def generate_model_identifier_string(obj: models.Model) -> str:
    if not isinstance(obj, models.Model):
        raise TypeError(
            f"obj must be an instance of Model or its subclass (was: {obj})"
        )
    name = camel_case_to_spaces(obj.__class__.__name__).replace(" ", "_")
    return f"{name}__id__{obj.id}"
