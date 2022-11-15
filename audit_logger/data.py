import datetime
import enum
import json
from dataclasses import Field, asdict, dataclass, field, fields, replace
from typing import Any, Optional, Type, Union

from django.db import models
from django.utils import timezone

from audit_logger import enums
from audit_logger.utils import (
    generate_model_id_string_from_class,
    generate_model_id_string_from_instance,
)


@dataclass
class ModelWithId:
    """
    Defines a model instance with a class and an id.
    """

    model: Type[models.Model]
    id: Any


class AuditMessageEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat(timespec="milliseconds")
        elif isinstance(o, models.Model):
            return generate_model_id_string_from_instance(o)
        elif isinstance(o, enum.Enum):
            return o.value
        elif isinstance(o, ModelWithId) and issubclass(o.model, models.Model):
            return generate_model_id_string_from_class(o.model, o.id)
        elif isinstance(o, models.QuerySet):
            return [generate_model_id_string_from_instance(obj) for obj in o]
        return super().default(o)


@dataclass
class AuditMessage:
    message: str = ""
    actor: models.Model = None
    target: Optional[Union[str, models.Model, ModelWithId]] = None
    operation: enums.Operation = None
    status: enums.Status = None
    reason: enums.Reason = None
    event_type: enums.EventType = enums.EventType.APP
    audit_type: enums.AuditType = enums.AuditType.AUDIT
    origin: str = ""
    version: str = "v1"
    extra: Optional[dict] = None
    log_level: Optional[enums.AuditLogLevel] = None

    # "Do not touch" params
    date_time: datetime.datetime = field(init=False, default_factory=timezone.now)

    def asdict(self):
        # asdict seems to use copy.deepcopy for the values, which doesn't work
        # 100% with Django models. Might be related to reversion.
        # Either way, we'll grab the models away from the message and add
        # them back after creating the dict.
        self_copy = self.replace(target=None, actor=None)
        d = asdict(self_copy)
        d["actor"] = self.actor
        d["target"] = self.target
        # replace will also reinitialize date_time, so need to add the
        # original value back as well.
        d["date_time"] = self.date_time
        return d

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
