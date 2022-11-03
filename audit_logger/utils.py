import logging

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
