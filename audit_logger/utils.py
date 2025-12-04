from typing import Type

from django.db import models
from django.utils.text import camel_case_to_spaces


def generate_model_id_string_from_instance(obj: models.Model) -> str:
    if not isinstance(obj, models.Model):
        raise TypeError(
            f"obj must be an instance of Model or its subclass (was: {obj})"
        )
    return generate_model_id_string_from_class(obj.__class__, obj.id)


def generate_model_id_string_from_class(model: Type[models.Model], id_) -> str:
    if not issubclass(model, models.Model):
        raise TypeError(f"obj must be Model or its subclass (was: {model})")
    name = camel_case_to_spaces(model.__name__).replace(" ", "_")
    return f"{name}__id__{id_}"
