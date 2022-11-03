import datetime
import enum
import json
from dataclasses import asdict, dataclass, field

from django.db import models
from django.utils import timezone

from audit_logger import enums


class AuditMessageEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat(timespec="milliseconds")
        elif isinstance(o, models.Model):
            return str(o)
        elif isinstance(o, enum.Enum):
            return o.value
        return super().default(o)


@dataclass
class AuditMessage:
    # Required params
    message: str
    actor: models.Model
    target: models.Model
    reason: enums.Reason
    operation: enums.Operation

    # Optional params/params with default values (for convenience)
    status: enums.Status = None
    event_type: enums.EventType = enums.EventType.APP
    audit_type: enums.AuditType = enums.AuditType.AUDIT
    origin: str = None
    version: str = "v1"
    log_level: enums.AuditLogLevel = None

    # "Do not touch" params
    date_time: datetime.datetime = field(init=False, default_factory=timezone.now)

    def asdict(self):
        return asdict(self)

    def __str__(self):
        s = AuditMessageEncoder().encode(self.asdict())
        return "%s >>> %s" % (self.message, s)
