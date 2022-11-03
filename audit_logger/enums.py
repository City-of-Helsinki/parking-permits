from enum import Enum


class Reason(Enum):
    """
    Usage explanation.
    """

    SELF_SERVICE = "SELF_SERVICE"
    """User did this operation themselves."""

    ADMIN_SERVICE = "ADMIN_SERVICE"
    """Admin did maintenance work because customer requested it."""

    MAINTENANCE = "MAINTENANCE"
    """Cronjob did maintenance work because of system rules."""


class Operation(Enum):
    """
    Performed operation.
    """

    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class Status(Enum):
    """
    Operation succeeded or failed.
    """

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class EventType(Enum):
    """
    Explicit type of event, to help categorise events.
    """

    APP = "APP"
    TRAFICOM = "TRAFICOM"
    DVV = "DVV"
    HELSINKI_PROFILE = "HELSINKI_PROFILE"
    TALPA = "TALPA"


class AuditType(Enum):
    """
    Explicit type of audit, is this audit event or not
    """

    APP = "APP"
    AUDIT = "AUDIT"


class AuditLogLevel(Enum):
    """
    Log level or severity.
    """

    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    ERROR = "ERROR"
