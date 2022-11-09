import datetime
import enum
import json
from dataclasses import Field, asdict, dataclass, field, fields, replace
from typing import Optional

from django.db import models
from django.utils import timezone

from audit_logger import enums
from audit_logger.utils import generate_model_identifier_string


class AuditMessageEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat(timespec="milliseconds")
        elif isinstance(o, models.Model):
            return generate_model_identifier_string(o)
        elif isinstance(o, enum.Enum):
            return o.value
        return super().default(o)


@dataclass
class AuditMessage:
    message: str = ""
    actor: models.Model = None
    target: Optional[models.Model] = None
    operation: enums.Operation = None
    status: enums.Status = None
    reason: enums.Reason = None
    event_type: enums.EventType = enums.EventType.APP
    audit_type: enums.AuditType = enums.AuditType.AUDIT
    origin: str = ""
    version: str = "v1"
    log_level: Optional[enums.AuditLogLevel] = None

    # "Do not touch" params
    date_time: datetime.datetime = field(init=False, default_factory=timezone.now)

    def asdict(self):
        return asdict(self)

    def replace(self, **changes):
        return replace(self, **changes)

    def set_defaults(self, **defaults):
        name_to_field: dict[str, Field] = {f.name: f for f in fields(self)}

        for k, v in defaults.items():
            if k not in name_to_field:
                continue
            f = name_to_field[k]
            if not f.init:
                continue
            if f.default == getattr(self, k):
                setattr(self, k, v)

    def __str__(self):
        s = AuditMessageEncoder().encode(self.asdict())
        return "%s >>> %s" % (self.message, s)
