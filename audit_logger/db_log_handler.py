import copy
import logging

from audit_logger.data import AuditMessage
from audit_logger.utils import get_audit_log_level

db_default_formatter = logging.Formatter()


class AuditLogHandler(logging.Handler):
    @staticmethod
    def makeAuditMessage(record) -> AuditMessage:
        msg = record.msg

        if isinstance(msg, AuditMessage):
            audit_msg = copy.copy(msg)
        else:
            raise TypeError(f"Message must be an AuditMessage (was: {type(msg)})")

        audit_msg.log_level = audit_msg.log_level or get_audit_log_level(record.levelno)

        return audit_msg

    @staticmethod
    def createAuditLogFromRecord(record):
        from .models import AuditLog

        msg = AuditLogHandler.makeAuditMessage(record)

        trace = None

        if record.exc_info:
            trace = db_default_formatter.formatException(record.exc_info)

        kwargs = {
            "logger_name": record.name,
            "level": record.levelno,
            "message": msg.asdict(),
            "trace": trace,
        }

        return AuditLog.objects.create(**kwargs)

    def emit(self, record):
        try:
            self.createAuditLogFromRecord(record)
        except Exception:
            self.handleError(record)
