"""Date constraints shared by customer and customer-service permit operations."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .exceptions import InvalidContractTypeError, ParkingPermitValidationError
from .utils import get_end_time

CONTRACT_TYPE_MISMATCH = _("Both permits must have the same contract type.")


def primary_end_limit(primary):
    # An ordinary subscription renewal date is not a contract end date.
    if (
        primary.contract_type == "FIXED_PERIOD"
        or primary.end_type == "AFTER_CURRENT_PERIOD"
    ):
        return primary.end_time
    return None


def get_secondary_end_time(start_time, month_count, primary):
    # Keep the primary's precision when both permits end in the same second.
    end_time = get_end_time(start_time, month_count)
    limit = primary_end_limit(primary) if primary else None
    if limit and end_time.replace(microsecond=0) == limit.replace(microsecond=0):
        return min(end_time, limit)
    return end_time


def _validate_secondary_basics(permit, primary, purchase):
    if purchase and (
        not isinstance(permit.month_count, int) or not 1 <= permit.month_count <= 12
    ):
        raise ParkingPermitValidationError(_("Month count exceeds maximum"))
    if primary is None:
        raise ParkingPermitValidationError(_("A primary permit is required."))
    if permit.start_time < primary.start_time:
        raise ParkingPermitValidationError(
            _("The second permit cannot start before the first permit.")
        )
    if permit.contract_type != primary.contract_type:
        raise InvalidContractTypeError(CONTRACT_TYPE_MISMATCH)


def _validate_open_ended_secondary_purchase(permit, limit, now):
    # Subscriptions have independent billing periods. They only need
    # to overlap when the secondary starts.
    if max(permit.start_time, now or timezone.now()) > limit:
        raise ParkingPermitValidationError(_("A primary permit is required."))


def _validate_secondary_end_time(permit, limit):
    if permit.end_time is None or permit.end_time > limit:
        raise ParkingPermitValidationError(
            _("The second permit cannot end after the first permit.")
        )


def _validate_fixed_period_secondary_purchase(permit, primary, limit, now):
    start = max(permit.start_time, now or timezone.now())
    if get_secondary_end_time(start, permit.month_count, primary) > limit:
        raise ParkingPermitValidationError(
            _(
                "The full duration of the second permit must fit before "
                "the first permit ends. Select a shorter duration."
            )
        )


def validate_secondary_permit(permit, primary, *, purchase=False, now=None):
    if permit.primary_vehicle:
        return
    _validate_secondary_basics(permit, primary, purchase)
    limit = primary_end_limit(primary)
    if limit is None:
        return
    if purchase and primary.contract_type == "OPEN_ENDED":
        _validate_open_ended_secondary_purchase(permit, limit, now)
        return
    _validate_secondary_end_time(permit, limit)
    if purchase and primary.contract_type == "FIXED_PERIOD":
        _validate_fixed_period_secondary_purchase(permit, primary, limit, now)
