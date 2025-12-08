import copy
import logging

from audit_logger.data import AuditMessage

db_default_formatter = logging.Formatter()


class AuditLogHandler(logging.Handler):
    @staticmethod
    def make_audit_message(record) -> AuditMessage:
        msg = record.msg

        if isinstance(msg, AuditMessage):
            audit_msg = copy.copy(msg)
        else:
            raise TypeError(f"Message must be an AuditMessage (was: {type(msg)})")

        audit_msg.log_level = audit_msg.log_level or record.levelno

        return audit_msg

    @staticmethod
    def create_audit_log_from_record(record):
        from resilient_logger.sources import ResilientLogSource

        msg = AuditLogHandler.make_audit_message(record)

        trace = None

        if record.exc_info:
            trace = db_default_formatter.formatException(record.exc_info)

        json = msg.safe_asdict()

        return ResilientLogSource.create_structured(
            message=msg.message,
            level=msg.log_level,
            operation=json["operation"],
            actor={"value": json["actor"]},
            target={"value": json["target"]},
            extra={
                "logger_name": record.name,
                "trace": trace,
                "status": json["status"],
                "reason": json["reason"],
                "event_type": json["event_type"],
                "audit_type": json["audit_type"],
                "origin": json["origin"],
                "version": json["version"],
            },
        )

    def emit(self, record):
        try:
            self.create_audit_log_from_record(record)
        except Exception:
            self.handleError(record)
