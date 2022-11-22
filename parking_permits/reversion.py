import datetime

from django.db import models
from reversion.models import Version

SEPARATOR = "|"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class EventType:
    CREATED = "CREATED"
    CHANGED = "CHANGED"


class FieldChangeResolver:
    def __init__(self, field, old_value, new_value):
        self.field = field
        self.old_value = old_value
        self.new_value = new_value

    @property
    def is_changed(self):
        if (
            isinstance(self.field, models.DateTimeField)
            and self.new_value
            and self.old_value
        ):
            # When saving serialized data into revisions, the
            # datatime values are serialized in the form of
            # YYYY-MM-DDTHH:mm:ss.sssZ or
            # YYYY-MM-DDTHH:mm:ss.sss+HH:MM as defined in ECMA-262
            # which removes the part after the milliseconds
            time_diff = abs(self.new_value - self.old_value)
            return time_diff > datetime.timedelta(milliseconds=1)

        return self.old_value != self.new_value

    @property
    def change_message(self):
        if isinstance(self.field, models.ForeignKey):
            # For related fields, only the primary keys
            # are serialized into the revision, thus
            # we fetch the instance and compare the
            # the difference of their string representations
            target_model = self.field.related_model
            old_instance = (
                self.old_value
                and target_model.objects.filter(pk=self.old_value).first()
            )
            new_instance = (
                self.new_value
                and target_model.objects.filter(pk=self.new_value).first()
            )
            return f"{self.field.verbose_name}: {old_instance} --> {new_instance}"
        elif isinstance(self.field, models.DateTimeField):
            format_old = self.old_value.strftime(TIME_FORMAT) if self.old_value else ""
            format_new = self.new_value.strftime(TIME_FORMAT) if self.new_value else ""
            return f"{self.field.verbose_name}: {format_old} --> {format_new}"

        return f"{self.field.verbose_name}: {self.old_value} --> {self.new_value}"


def _created_description_resolver(obj):
    model_class = type(obj)
    return f"{model_class._meta.verbose_name}: {obj}"


def _changed_description_resolver(obj):
    version = Version.objects.get_for_object(obj).first()
    if not version:
        return ""

    old_data = version.field_dict
    new_data = vars(obj)

    changes = []
    model_class = type(obj)
    for field_key, new_value in new_data.items():
        if field_key == "_state":
            continue
        field = model_class._meta.get_field(field_key)
        old_value = old_data.get(field_key)
        change_resolver = FieldChangeResolver(field, old_value, new_value)
        if change_resolver.is_changed:
            changes.append(change_resolver.change_message)
    return ", ".join(changes)


description_resolvers = {
    EventType.CREATED: _created_description_resolver,
    EventType.CHANGED: _changed_description_resolver,
}


def get_reversion_comment(event, obj):
    description_resolver = description_resolvers[event]
    description = description_resolver(obj)
    return f"{event}{SEPARATOR}{description}"


def get_obj_changelogs(obj):
    versions = Version.objects.get_for_object(obj)
    data = []
    for version in versions:
        user = version.revision.user
        event, description = version.revision.comment.split(SEPARATOR)
        item = {
            "id": version.id,
            "event": event,
            "description": description,
            "created_at": version.revision.date_created,
            "created_by": str(version.revision.user) if user else "",
        }
        data.append(item)
    return data
