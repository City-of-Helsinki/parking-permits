import logging

from ariadne.utils import unwrap_graphql_error

from audit_logger.utils import EXCEPTION_SUMMARY_ATTR, format_exception_summary
from parking_permits.exceptions import ParkingPermitValidationError


class ValidationErrorSummaryFilter(logging.Filter):
    """
    Logging filter that strips the traceback from log records of expected
    validation errors and replaces the message with a one-line summary,
    e.g. "AddressError: Permit address does not have a valid zone".

    Records of any other exceptions are passed through unchanged.

    The summary is also stored in the record's ``EXCEPTION_SUMMARY_ATTR``
    attribute, which marks the record as an expected validation error.

    The filter never drops records; it returns the (possibly modified)
    record.
    """

    expected_exceptions: tuple[type[BaseException], ...] = (
        ParkingPermitValidationError,
    )

    def filter(self, record: logging.LogRecord) -> logging.LogRecord:
        if not record.exc_info:
            return record

        exc = unwrap_graphql_error(record.exc_info[1])
        if isinstance(exc, self.expected_exceptions):
            summary = format_exception_summary(exc)
            record.msg = summary
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            setattr(record, EXCEPTION_SUMMARY_ATTR, summary)

        return record
