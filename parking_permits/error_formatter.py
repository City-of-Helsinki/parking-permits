from ariadne import format_error
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import ParkingPermitBaseException


def error_formatter(error, debug):
    formatted = format_error(error, debug)
    if isinstance(error.original_error, ParkingPermitBaseException):
        formatted["message"] = str(error.original_error)
    elif isinstance(error.original_error, PermissionDenied):
        formatted["message"] = _("Forbidden")
    else:
        formatted["message"] = _("Internal Server Error")
    return formatted
