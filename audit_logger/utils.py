from django.db import models
from django.utils.text import camel_case_to_spaces

# Name of the LogRecord attribute that holds a one-line exception summary
# for exceptions that are logged without a traceback.
EXCEPTION_SUMMARY_ATTR = "exception_summary"


def format_exception_summary(exc: BaseException) -> str:
    """
    Return a one-line summary of the exception without a traceback,
    e.g. "AddressError: Permit address does not have a valid zone".

    If the exception was explicitly chained (``raise ... from cause``),
    the cause is appended so that its details are not lost.
    """
    name = type(exc).__name__
    message = str(exc)
    summary = f"{name}: {message}" if message else name

    cause = exc.__cause__
    if cause is not None:
        summary = f"{summary} (caused by {format_exception_summary(cause)})"

    return summary


def generate_model_id_string_from_instance(obj: models.Model) -> str:
    if not isinstance(obj, models.Model):
        raise TypeError(
            f"obj must be an instance of Model or its subclass (was: {obj})"
        )
    return generate_model_id_string_from_class(obj.__class__, obj.id)


def generate_model_id_string_from_class(model: type[models.Model], id_) -> str:
    if not issubclass(model, models.Model):
        raise TypeError(f"obj must be Model or its subclass (was: {model})")
    name = camel_case_to_spaces(model.__name__).replace(" ", "_")
    return f"{name}__id__{id_}"
