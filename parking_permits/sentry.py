"""
Sentry SDK hooks.

This module is imported from the Django settings, so it must not import
anything at module level that requires the settings to be loaded
(e.g. Django models).
"""

import logging

from ariadne.utils import unwrap_graphql_error

from parking_permits.exceptions import ParkingPermitValidationError


def is_validation_error(exc: BaseException | None) -> bool:
    """
    Return True if the exception is an expected validation error.

    Exceptions raised in GraphQL resolvers are wrapped in a ``GraphQLError``,
    so the original error is unwrapped first.
    """
    return isinstance(unwrap_graphql_error(exc), ParkingPermitValidationError)


def _is_validation_error_log_record(record: logging.LogRecord) -> bool:
    from audit_logger.utils import EXCEPTION_SUMMARY_ATTR

    return getattr(record, EXCEPTION_SUMMARY_ATTR, None) is not None


def before_send(event, hint):
    """
    Drop events of expected validation errors (i.e. invalid input or
    a violated business rule), they are not errors in the service.

    Validation errors reach Sentry through several integrations:

    - Ariadne integration captures every GraphQL error, where the original
      exception is wrapped in a ``GraphQLError``.
    - Django integration captures unhandled exceptions raised in views.
    - Logging integration captures error log records, e.g. audit log records
      of failed operations, which are logged without the exception itself.
    """
    exc_info = hint.get("exc_info")
    if exc_info and is_validation_error(exc_info[1]):
        return None

    log_record = hint.get("log_record")
    if log_record is not None and _is_validation_error_log_record(log_record):
        return None

    return event
