import decimal

import reversion
from dateutil.parser import isoparse, parse
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone as tz

from .constants import LOW_EMISSION_DISCOUNT, SECONDARY_VEHICLE_PRICE_INCREASE
from .exceptions import (
    InvalidContractType,
    InvalidUserZone,
    NonDraftPermitUpdateError,
    PermitCanNotBeDelete,
    PermitLimitExceeded,
    RefundError,
)
from .mock_vehicle import get_mock_vehicle
from .models import Customer, OrderItem, ParkingPermit, ParkingZone, Refund
from .models.parking_permit import (
    ContractType,
    ParkingPermitStartType,
    ParkingPermitStatus,
)
from .reversion import EventType, get_reversion_comment
from .utils import diff_months_floor, get_end_time

IMMEDIATELY = ParkingPermitStartType.IMMEDIATELY
OPEN_ENDED = ContractType.OPEN_ENDED
DRAFT = ParkingPermitStatus.DRAFT
VALID = ParkingPermitStatus.VALID
PROCESSING = ParkingPermitStatus.PROCESSING
FROM = ParkingPermitStartType.FROM
FIXED_PERIOD = ContractType.FIXED_PERIOD


def next_day():
    return tz.localtime(tz.now() + tz.timedelta(days=1))


def two_week_from_now():
    return tz.localtime(tz.now() + tz.timedelta(weeks=2))


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
                permit.end_time = get_end_time(next_day(), permit.month_count)
                permit.save(update_fields=["start_time", "end_time"])
            products = []
            for product_with_qty in permit.get_products_with_quantities():
                product = self._calculate_prices(permit, product_with_qty)
                if product.quantity:
                    products.append(product)
            permit.products = products
            if permit.can_be_refunded:
                permit.refund_amount = permit.get_refund_amount_for_unused_items()
            permits.append(permit)
        return permits

    def create(self, zone_id):
        if self._can_buy_permit_for_zone(zone_id):
            contract_type = OPEN_ENDED
            primary_vehicle = True
            end_time = None
            if self.customer_permit_query.count():
                primary_permit = self.customer_permit_query.get(primary_vehicle=True)
                contract_type = primary_permit.contract_type
                primary_vehicle = not primary_permit.primary_vehicle
                if contract_type == FIXED_PERIOD:
                    end_time = primary_permit.end_time

            with reversion.create_revision():
                permit = ParkingPermit.objects.create(
                    customer=self.customer,
                    parking_zone=ParkingZone.objects.get(id=zone_id),
                    primary_vehicle=primary_vehicle,
                    contract_type=contract_type,
                    start_time=next_day(),
                    end_time=end_time,
                    vehicle=get_mock_vehicle(self.customer, ""),
                )
                comment = get_reversion_comment(EventType.CREATED, permit)
                reversion.set_user(self.customer.user)
                reversion.set_comment(comment)
                return permit

    def delete(self, permit_id):
        permit = ParkingPermit.objects.get(customer=self.customer, id=permit_id)
        if permit.status != DRAFT:
            raise PermitCanNotBeDelete("Non draft permit can not be deleted")
        permit.delete()

        if self.customer_permit_query.count():
            other_permit = self.customer_permit_query.first()
            data = {"primary_vehicle": True}
            self._update_permit(other_permit, data)
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
            permit.vehicle.consent_low_emission_accepted = data.get(
                "consent_low_emission_accepted", False
            )
            permit.vehicle.save(update_fields=["consent_low_emission_accepted"])
            return permit

        if "primary_vehicle" in keys:
            return self._toggle_primary_permit()

        if "zone_id" in keys and self._can_buy_permit_for_zone(data["zone_id"]):
            fields_to_update.update({"parking_zone_id": data["zone_id"]})

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
                    month_count = self._get_month_count_for_primary_permit(
                        contract_type, month_count
                    )
                    if secondary and secondary.month_count > month_count:
                        permit_to_update.append(secondary.id)
                else:
                    month_count = self._get_month_count_for_secondary_permit(
                        contract_type, month_count
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
                return [
                    self._update_permit(
                        self.customer_permit_query.get(id=id), fields_to_update
                    )
                    for id in permit_to_update
                ]

        return self._update_fields_to_all_draft(fields_to_update)

    def end(self, permit_ids, end_type, iban=None):
        for permit_id in permit_ids:
            with reversion.create_revision():
                permit = ParkingPermit.objects.get(id=permit_id)
                permit.end_permit(end_type)
                permit.update_parkkihubi_permit()
                if permit.can_be_refunded:
                    if not iban:
                        raise RefundError("IBAN is not provided")
                    description = f"Refund for ending permit #{permit.identifier}"
                    Refund.objects.create(
                        name=str(permit.customer),
                        order=permit.order,
                        amount=permit.get_refund_amount_for_unused_items(),
                        iban=iban,
                        description=description,
                    )

                reversion.set_user(self.customer.user)
                comment = get_reversion_comment(EventType.CHANGED, permit)
                reversion.set_comment(comment)
        # Delete all the draft permit while ending the customer valid permits
        draft_permits = self.customer_permit_query.filter(status=DRAFT)
        OrderItem.objects.filter(permit__in=draft_permits).delete()
        draft_permits.delete()
        return True

    def _update_fields_to_all_draft(self, data):
        permits = self.customer_permit_query.filter(status=DRAFT).all()
        return [self._update_permit(permit, data) for permit in permits]

    def _update_permit(self, permit, data):
        keys = data.keys()
        for key in keys:
            if isinstance(data[key], str) and key in ["start_time", "end_time"]:
                val = isoparse(data[key])
            else:
                val = data[key]
            setattr(permit, key, val)
        permit.save(update_fields=keys)
        return permit

    def _calculate_prices(self, permit, product_with_qty):
        product = product_with_qty[0]
        quantity = product_with_qty[1]
        unit_price = product.unit_price

        if not permit.primary_vehicle:
            increase = decimal.Decimal(SECONDARY_VEHICLE_PRICE_INCREASE) / 100
            unit_price += increase * unit_price

        if permit.vehicle.is_low_emission:
            discount = decimal.Decimal(LOW_EMISSION_DISCOUNT) / 100
            unit_price -= discount * unit_price

        product.quantity = quantity
        product.unit_price = unit_price
        product.total_price = unit_price * quantity
        return product

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
        return primary, secondary

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

    def _get_month_count_for_secondary_permit(self, contract_type, count):
        if contract_type == OPEN_ENDED:
            return 1
        primary, secondary = self._get_primary_and_secondary_permit()
        end_date = primary.end_time
        if not end_date:
            return 12 if count > 12 else count

        month_diff = diff_months_floor(next_day(), end_date)
        dangling_days = (end_date - get_end_time(next_day(), month_diff)).days

        month_count = month_diff + 1 if dangling_days >= 1 else month_diff
        return month_count if count > month_count else count

    def _get_month_count_for_primary_permit(self, contract_type, month_count):
        if contract_type == OPEN_ENDED:
            return 1
        if month_count > 12:
            return 12
        if month_count < 1:
            return 1
        return month_count
