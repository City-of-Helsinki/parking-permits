from ariadne import format_error
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from parking_permits.exceptions import (
    ParkingPermitBaseException,
    TraficomFetchVehicleError,
)


def error_formatter(error, debug):
    return {
        **format_error(error, debug),
        "message": get_error_message(error.original_error),
    }


def get_error_message(exc):
    if isinstance(exc, TraficomFetchVehicleError):
        return f"{exc}\n{_('Source: Transport register, Traficom')}"
    if isinstance(exc, ParkingPermitBaseException):
        return str(exc)
    if isinstance(exc, PermissionDenied):
        return _("Forbidden")
    return _("Internal Server Error")
