from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone as tz

from . import constants
from .exceptions import (
    InvalidContractType,
    InvalidUserZone,
    NonDraftPermitUpdateError,
    PermitLimitExceeded,
)
from .mock_vehicle import get_mock_vehicle
from .models import Customer, ParkingPermit, ParkingZone
from .services.talpa import resolve_price_response
from .utils import calc_months_diff

IMMEDIATELY = constants.StartType.IMMEDIATELY.value
OPEN_ENDED = constants.ContractType.OPEN_ENDED.value
DRAFT = constants.ParkingPermitStatus.DRAFT.value
VALID = constants.ParkingPermitStatus.VALID.value
PROCESSING = constants.ParkingPermitStatus.PROCESSING.value
FROM = constants.StartType.FROM.value
FIXED_PERIOD = constants.ContractType.FIXED_PERIOD.value


def next_day():
    return tz.localtime(tz.now() + tz.timedelta(days=1))


def two_week_from_now():
    return tz.localtime(tz.now() + tz.timedelta(weeks=2))


def get_end_time(start, month=0):
    return tz.localtime(start + relativedelta(months=month))


class CustomerPermit:
    customer = None
    customer_permit_query = None

    def __init__(self, customer_id):
        self.customer = Customer.objects.get(id=customer_id)
        self.customer_permit_query = ParkingPermit.objects.filter(
            customer=self.customer, status__in=[VALID, PROCESSING, DRAFT]
        )

    def get(self):
        permits = []
        # Update the start_time to next day for all the draft permits
        for permit in self.customer_permit_query.order_by("start_time"):
            if permit.status == DRAFT:
                permit.start_time = next_day()
                permit.save(update_fields=["start_time"])
            permits.append(self._resolve_prices(permit))
        return permits

    def create(self, zone_id):
        if self._can_buy_permit_for_zone(zone_id):
            contract_type = OPEN_ENDED
            primary_vehicle = True
            if self.customer_permit_query.count():
                primary_permit = self.customer_permit_query.get(primary_vehicle=True)
                contract_type = primary_permit.contract_type
                primary_vehicle = not primary_permit.primary_vehicle

            permit = ParkingPermit.objects.create(
                customer=self.customer,
                parking_zone=ParkingZone.objects.get(id=zone_id),
                primary_vehicle=primary_vehicle,
                contract_type=contract_type,
                start_time=next_day(),
                vehicle=get_mock_vehicle(self.customer, ""),
            )
            return permit

    def delete(self, permit_id):
        self.customer_permit_query.get(id=permit_id).delete()

        if self.customer_permit_query.count():
            other_permit = self.customer_permit_query.first()
            other_permit.primary_vehicle = True
            other_permit.save(update_fields=["primary_vehicle"])

        return True

    def update(self, data, permit_id=None):
        keys = data.keys()
        fields_to_update = {}

        # TODO: this is a remporary solution for now. It should be removed and the field
        #  needs to be updated when a notification is received from talpa
        if "order_id" in keys:
            fields_to_update.update(
                {"order_id": data["order_id"], "status": PROCESSING}
            )

        if "consent_low_emission_accepted" in keys:
            permit, is_primary = self._get_permit(permit_id)
            permit.consent_low_emission_accepted = data.get(
                "consent_low_emission_accepted", False
            )
            return permit.save(update_fields=["consent_low_emission_accepted"])

        if "primary_vehicle" in keys:
            return self._toggle_primary_permit()

        if "zone_id" in keys and self._can_buy_permit_for_zone(data["zone_id"]):
            fields_to_update.update({"parking_zone": data["zone_id"]})

        if "start_type" in keys or "start_time" in keys:
            fields_to_update.update(self._get_start_type_and_start_time(data))

        if "contract_type" in keys or "month_count" in keys:
            permit_to_update = [permit_id]
            contract_type = data.get("contract_type", None)
            month_count = data.get("month_count", 1)
            primary, secondary = self._get_primary_and_secondary_permit()
            end_time = get_end_time(primary.start_time, month_count)
            if not contract_type:
                raise InvalidContractType("Contract type is required")

            # Second permit can not be open ended if primary permit valid or processing and is fixed period
            if (
                primary.status != DRAFT
                and primary.contract_type == FIXED_PERIOD
                and contract_type != FIXED_PERIOD
            ):
                raise InvalidContractType(f"Only {FIXED_PERIOD} is allowed")

            if permit_id:
                permit, is_primary = self._get_permit(permit_id)

                if permit.status != DRAFT:
                    raise NonDraftPermitUpdateError(
                        "This is not a draft permit and can not be edited"
                    )

                if is_primary:
                    month_count = self._get_month_count_for_primary_permit(month_count)
                    if secondary and secondary.month_count > month_count:
                        permit_to_update.append(secondary.id)
                else:
                    month_count = self._get_month_count_for_secondary_permit(
                        month_count
                    )
                    sec_p_end_time = get_end_time(secondary.start_time, month_count)
                    end_time = end_time if sec_p_end_time > end_time else sec_p_end_time

            fields_to_update.update(
                {
                    "contract_type": data["contract_type"],
                    "month_count": month_count,
                    "end_time": end_time,
                }
            )
            if permit_id:
                return self.customer_permit_query.filter(
                    id__in=permit_to_update
                ).update(**fields_to_update)

        return self._update_fields_to_all_draft(fields_to_update)

    def _update_fields_to_all_draft(self, data):
        return self.customer_permit_query.filter(status=DRAFT).update(**data)

    def _resolve_prices(self, permit):
        total_price, monthly_price = permit.get_prices()
        permit.prices = resolve_price_response(total_price, monthly_price)
        return permit

    def _can_buy_permit_for_zone(self, zone_id):
        if not self._is_valid_user_zone(zone_id):
            raise InvalidUserZone("Invalid user zone.")

        max_allowed_permit = settings.MAX_ALLOWED_USER_PERMIT

        # User can not exceed max allowed permit per user
        if self.customer_permit_query.count() > max_allowed_permit:
            raise PermitLimitExceeded(
                f"You can have a max of {max_allowed_permit} permits."
            )

        # If user has existing permit that is in valid or processing state then
        # the zone id from it should be used as he can have multiple permit for
        # multiple zone.
        if self.customer_permit_query.count():
            primary, _ = self._get_primary_and_secondary_permit()
            if str(primary.parking_zone_id) != zone_id and primary.status != DRAFT:
                raise InvalidUserZone(
                    f"You can buy permit only for zone {primary.parking_zone.name}"
                )

        return True

    def _is_valid_user_zone(self, zone_id):
        primary = self.customer.primary_address
        other = self.customer.other_address

        # Check if zone belongs to either of the user address zone
        if primary and str(primary.zone_id) == zone_id:
            return True
        if other and str(other.zone_id) == zone_id:
            return True
        return False

    def _get_primary_and_secondary_permit(self):
        primary = self.customer_permit_query.get(primary_vehicle=True)
        secondary = None
        try:
            secondary = self.customer_permit_query.get(primary_vehicle=False)
        except ObjectDoesNotExist:
            pass
        return primary, secondary

    def _get_permit(self, permit_id):
        permit = self.customer_permit_query.get(id=permit_id)
        return permit, permit.primary_vehicle

    def _toggle_primary_permit(self):
        primary, secondary = self._get_primary_and_secondary_permit()
        if not secondary:
            return [primary]
        primary.primary_vehicle = secondary.primary_vehicle
        primary.save(update_fields=["primary_vehicle"])
        secondary.primary_vehicle = not secondary.primary_vehicle
        secondary.save(update_fields=["primary_vehicle"])
        return [primary, secondary]

    # Start time will be next day by default if the type is immediately
    # but if the start type is FROM then the start time can not be
    # now or in the past also it can not be more than two weeks in future.
    def _get_start_type_and_start_time(self, data):
        start_type = data.get("start_type", None)
        start_time = data.get("start_time", next_day())

        if start_time and not start_type:
            start_type = FROM

        if not data.get("start_time", None) and not start_type:
            start_type = IMMEDIATELY

        if start_type == FROM:
            parsed = tz.localtime(parse(start_time))
            start_time = (
                two_week_from_now()
                if parsed.date() > two_week_from_now().date()
                else parsed
            )
        return {"start_type": start_type, "start_time": start_time}

    def _get_month_count_for_secondary_permit(self, count):
        primary, secondary = self._get_primary_and_secondary_permit()
        end_date = primary.end_time
        if not end_date:
            return 12 if count > 12 else count

        month_diff = calc_months_diff(next_day(), end_date)
        dangling_days = (end_date - get_end_time(next_day(), month_diff)).days

        month_count = month_diff + 1 if dangling_days >= 1 else month_diff
        return month_count if count > month_count else count

    def _get_month_count_for_primary_permit(self, month_count):
        if month_count > 12:
            return 12
        if month_count < 1:
            return 1
        return month_count
