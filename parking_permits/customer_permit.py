import decimal
import logging
import typing

from dateutil.parser import isoparse, parse
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _

from .constants import SECONDARY_VEHICLE_PRICE_INCREASE, EventFields
from .exceptions import (
    DuplicatePermit,
    InvalidContractType,
    InvalidUserAddress,
    NonDraftPermitUpdateError,
    PermitCanNotBeDeleted,
    PermitCanNotBeExtended,
    PermitLimitExceeded,
    TemporaryVehicleValidationError,
    TraficomFetchVehicleError,
)
from .models import (
    Address,
    Customer,
    Order,
    OrderItem,
    ParkingPermit,
    Refund,
    Subscription,
    TemporaryVehicle,
    Vehicle,
)
from .models.order import (
    OrderPaymentType,
    OrderStatus,
    OrderType,
    SubscriptionCancelReason,
)
from .models.parking_permit import (
    ContractType,
    ParkingPermitEventFactory,
    ParkingPermitStartType,
    ParkingPermitStatus,
)
from .services.mail import (
    PermitEmailType,
    RefundEmailType,
    send_permit_email,
    send_refund_email,
    send_vehicle_low_emission_discount_email,
)
from .utils import ModelDiffer, diff_months_floor, get_end_time

logger = logging.getLogger("db")

IMMEDIATELY = ParkingPermitStartType.IMMEDIATELY
OPEN_ENDED = ContractType.OPEN_ENDED
DRAFT = ParkingPermitStatus.DRAFT
VALID = ParkingPermitStatus.VALID
PAYMENT_IN_PROGRESS = ParkingPermitStatus.PAYMENT_IN_PROGRESS
CANCELLED = ParkingPermitStatus.CANCELLED
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
            customer=self.customer, status__in=[VALID, PAYMENT_IN_PROGRESS, DRAFT]
        )

    def create_permit_extension_request(
        self,
        permit_id,
        month_count,
        *,
        payment_type=OrderPaymentType.ONLINE_PAYMENT,
    ):
        """Creates a Pending extension request.

        Raises PermitCanNotBeExtended if extensions are not allowed for this permit.
        """
        permit, _primary_vehicle = self._get_permit(permit_id)
        if not permit.can_extend_permit:
            raise PermitCanNotBeExtended(_("You cannot extend this permit."))

        if month_count > permit.max_extension_month_count:
            raise PermitCanNotBeExtended(_("Month count exceeds maximum"))

        order = Order.objects.create_for_extended_permit(
            permit,
            month_count,
            status=OrderStatus.DRAFT,
            type=OrderType.CREATED,
            payment_type=payment_type,
        )

        return permit.permit_extension_requests.create(
            order=order,
            month_count=month_count,
        )

    def add_temporary_vehicle(self, permit_id, registration, start_time, end_time):
        has_valid_permit = self.customer_permit_query.filter(
            vehicle__registration_number=registration
        ).exists()

        if has_valid_permit:
            raise TemporaryVehicleValidationError(
                _("You already have a valid permit for a given vehicle.")
            )

        permit_details = self._get_permit(permit_id)
        permit = permit_details[0]

        if tz.localtime(isoparse(start_time)) < permit.start_time:
            raise TemporaryVehicleValidationError(
                _("Temporary vehicle start time has to be after permit start time")
            )

        tmp_vehicles = permit.temp_vehicles.filter(
            start_time__gte=get_end_time(tz.now(), -12)
        ).order_by("-start_time")[:2]

        if tmp_vehicles.count() == 2:
            raise TemporaryVehicleValidationError(
                _(
                    "Can not have more than 2 temporary vehicles in 365 days from first one."
                )
            )

        vehicle = TemporaryVehicle.objects.create(
            vehicle=Vehicle.objects.get(registration_number=registration),
            end_time=end_time,
            start_time=start_time,
        )
        permit.temp_vehicles.add(vehicle)
        ParkingPermitEventFactory.make_add_temporary_vehicle_event(
            permit, vehicle, created_by=self.customer.user
        )
        permit.update_parkkihubi_permit()
        send_permit_email(PermitEmailType.TEMP_VEHICLE_ACTIVATED, permit)
        return True

    def remove_temporary_vehicle(self, permit_id):
        permit_details = self._get_permit(permit_id)
        permit = permit_details[0]
        active_temp_vehicles = permit.temp_vehicles.filter(is_active=True)
        prev_active_temp_vehicles = list(active_temp_vehicles)
        active_temp_vehicles.update(is_active=False)
        for temp_vehicle in prev_active_temp_vehicles:
            ParkingPermitEventFactory.make_add_temporary_vehicle_event(
                permit, temp_vehicle, created_by=self.customer.user
            )
        permit.update_parkkihubi_permit()
        send_permit_email(PermitEmailType.TEMP_VEHICLE_DEACTIVATED, permit)
        return True

    def get(self):
        permits = []
        # Delete all the draft permits if it wasn't created today
        draft_permits = self.customer_permit_query.filter(
            status=DRAFT, start_time__lt=tz.localdate(tz.now())
        ).all()
        for permit in draft_permits:
            permit.order_items.all().delete()
            permit.delete()

        for permit in self.customer_permit_query.order_by("start_time"):
            permit.temporary_vehicles.filter(end_time__lt=tz.now()).update(
                is_active=False
            )
            # vehicle = permit.vehicle
            # Update vehicle detail from traficom if it wasn't updated today
            # if (
            #    not permit.vehicle.updated_from_traficom_on
            #    or permit.vehicle.updated_from_traficom_on < tz.localdate(tz.now())
            # ):
            #    vehicle = self.customer.fetch_vehicle_detail(
            #        vehicle.registration_number,
            #        permit=permit,
            #    )

            # Temporarily disable vehicle user check
            # user_of_vehicle = self.customer.is_user_of_vehicle(vehicle)
            # if not user_of_vehicle:
            #    permit.vehicle_changed = True
            #    permit.vehicle_changed_date = tz.localdate(tz.now())
            #    permit.save()
            products = []
            for product_with_qty in permit.get_products_with_quantities():
                product = self._calculate_prices(permit, product_with_qty)
                if product.quantity:
                    products.append(product)
            permit.products = products

            # automatically cancel permit and it's latest order if payment is not completed in configured time
            # (default 15 minutes)
            payment_wait_time_buffer = (
                settings.TALPA_ORDER_PAYMENT_WEBHOOK_WAIT_BUFFER_MINS
            )
            if (
                permit.status == PAYMENT_IN_PROGRESS
                and permit.latest_order
                and tz.localtime(
                    permit.latest_order.talpa_last_valid_purchase_time
                    + tz.timedelta(minutes=payment_wait_time_buffer)
                )
                < tz.localtime(tz.now())
            ):
                permit.status = CANCELLED
                latest_order = permit.latest_order
                latest_order.status = OrderStatus.CANCELLED
                latest_order.save()
                permit.save()
            permits.append(permit)
        return permits

    def create(self, address_id, registration):
        if self.customer_permit_query.filter(
            vehicle__registration_number=registration
        ).count():
            raise DuplicatePermit(_("Permit for a given vehicle already exist."))
        address = Address.objects.get(id=address_id)
        if self._can_buy_permit_for_address(address.id):
            contract_type = OPEN_ENDED
            primary_vehicle = True
            primary_end_time = None
            if self.customer_permit_query.count():
                primary_permit = self.customer_permit_query.get(primary_vehicle=True)
                contract_type = primary_permit.contract_type
                primary_vehicle = not primary_permit.primary_vehicle
                primary_end_time = primary_permit.end_time

            if settings.TRAFICOM_CHECK:
                self.customer.fetch_driving_licence_detail()

            vehicle = self.customer.fetch_vehicle_detail(registration)
            if settings.TRAFICOM_CHECK:
                is_user_of_vehicle = self.customer.is_user_of_vehicle(vehicle)
                if not is_user_of_vehicle:
                    raise TraficomFetchVehicleError(
                        _(
                            "Owner/holder data of a vehicle could not be verified. "
                            "Please check with Traficom for data transfer restrictions."
                        )
                    )

                has_valid_licence = self.customer.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
                if not has_valid_licence:
                    raise TraficomFetchVehicleError(
                        _("Customer does not have a valid driving licence")
                    )

            start_time = tz.now()
            end_time = get_end_time(start_time, 1)
            if primary_end_time:
                end_time = min(end_time, primary_end_time)

            address_apartment, address_apartment_sv = self._get_address_apartments(
                address
            )
            permit = ParkingPermit.objects.create(
                customer=self.customer,
                address=address,
                address_apartment=address_apartment,
                address_apartment_sv=address_apartment_sv,
                parking_zone=address.zone,
                primary_vehicle=primary_vehicle,
                contract_type=contract_type,
                start_time=start_time,
                end_time=end_time,
                vehicle=Vehicle.objects.get(registration_number=registration),
            )

            ParkingPermitEventFactory.make_create_permit_event(
                permit, created_by=self.customer.user
            )

            return permit

    def delete(self, permit_id):
        permit = ParkingPermit.objects.get(customer=self.customer, id=permit_id)
        if permit.status != DRAFT:
            raise PermitCanNotBeDeleted(_("Non draft permit can not be deleted"))
        OrderItem.objects.filter(permit=permit).delete()
        permit.delete()

        if self.customer_permit_query.count():
            other_permit = self.customer_permit_query.first()
            data = {"primary_vehicle": True}
            self._update_permit(other_permit, data)
        return True

    def update(self, data, permit_id=None):
        keys = data.keys()
        fields_to_update = {}

        if "order_id" in keys:
            fields_to_update.update(
                {"order_id": data["order_id"], "status": PAYMENT_IN_PROGRESS}
            )

        if "consent_low_emission_accepted" in keys:
            permit, is_primary = self._get_permit(permit_id)
            permit.vehicle.consent_low_emission_accepted = data.get(
                "consent_low_emission_accepted", False
            )
            permit.vehicle.save(update_fields=["consent_low_emission_accepted"])
            return [permit]

        if "primary_vehicle" in keys:
            return self._toggle_primary_permit()

        if "address_id" in keys:
            address = Address.objects.get(id=data["address_id"])
            if self._can_buy_permit_for_address(address.id):
                fields_to_update.update(
                    {
                        "address_id": data["address_id"],
                        "parking_zone_id": address.zone.id,
                    }
                )

        if "start_type" in keys or "start_time" in keys:
            fields_to_update.update(self._get_start_type_and_start_time(data))

        if "contract_type" in keys or "month_count" in keys:
            permit_to_update = [permit_id]
            contract_type = data.get("contract_type", None)
            month_count = data.get("month_count", 1)
            primary, secondary = self._get_primary_and_secondary_permit()
            end_time = get_end_time(primary.start_time, month_count)

            if not contract_type:
                raise InvalidContractType(_("Contract type is required"))

            # Second permit can not be open ended if primary permit valid or processing and is fixed period
            if (
                primary.status != DRAFT
                and primary.contract_type == FIXED_PERIOD
                and contract_type != FIXED_PERIOD
            ):
                raise InvalidContractType(
                    _("Only %(fixed_period)s is allowed")
                    % {"fixed_period": FIXED_PERIOD}
                )

            if permit_id:
                permit, is_primary = self._get_permit(permit_id)

                if permit.status != DRAFT:
                    raise NonDraftPermitUpdateError(
                        _("This is not a draft permit and can not be edited")
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

    def end(
        self,
        permit_ids,
        end_type,
        iban=None,
        user=None,
        subscription_cancel_reason=SubscriptionCancelReason.USER_CANCELLED,
        cancel_from_talpa=True,
        force_end=False,
    ):
        logger.info(
            f"Ending permits: {','.join([str(permit_id) for permit_id in permit_ids])}"
        )
        permits = self.customer_permit_query.filter(id__in=permit_ids).order_by(
            "primary_vehicle"
        )
        if all(permit.can_be_refunded for permit in permits):
            total_sum = sum(
                [permit.get_refund_amount_for_unused_items() for permit in permits]
            )
            first_permit = permits.first()
            refund = Refund.objects.filter(order=first_permit.latest_order)
            if refund.exists():
                order = Order.objects.create_renewal_order(
                    first_permit.customer,
                    status=OrderStatus.CONFIRMED,
                    order_type=OrderType.CREATED,
                    payment_type=OrderPaymentType.ONLINE_PAYMENT,
                    user=user,
                    create_renew_order_event=False,
                )
                total_sum = order.total_price
                order.order_items.all().delete()
            else:
                order = first_permit.latest_order
            if (
                total_sum > 0
                and first_permit.contract_type == ContractType.FIXED_PERIOD
            ):
                refund = Refund.objects.create(
                    name=self.customer.full_name,
                    order=order,
                    amount=total_sum,
                    iban=iban,
                    description=f"Refund for ending permits {','.join([str(permit.id) for permit in permits])}",
                )
                refund.permits.set(permits)
                send_refund_email(RefundEmailType.CREATED, self.customer, refund)

                for permit in permits:
                    ParkingPermitEventFactory.make_create_refund_event(
                        permit, refund, created_by=self.customer.user
                    )

        for permit in permits:
            if permit.contract_type == ContractType.OPEN_ENDED:
                subscription = (
                    Subscription.objects.filter(order_items__permit__pk=permit.pk)
                    .distinct()
                    .first()
                )
                if subscription:
                    subscription.cancel(
                        cancel_reason=subscription_cancel_reason,
                        cancel_from_talpa=cancel_from_talpa,
                        iban=iban,
                    )
            else:
                # Cancel fixed period permit order when this is the last valid permit in that order
                latest_order = permit.latest_order
                if (
                    latest_order
                    and not latest_order.order_permits.filter(status=[VALID])
                    .exclude(pk=permit.pk)
                    .exists()
                ):
                    latest_order.cancel(cancel_from_talpa=cancel_from_talpa)

            active_temporary_vehicle = permit.active_temporary_vehicle
            if active_temporary_vehicle:
                active_temporary_vehicle.is_active = False
                active_temporary_vehicle.save()

            if permit.consent_low_emission_accepted and permit.vehicle.is_low_emission:
                send_vehicle_low_emission_discount_email(
                    PermitEmailType.VEHICLE_LOW_EMISSION_DISCOUNT_DEACTIVATED,
                    permit,
                )

            permit.end_permit(end_type, force_end=force_end)
            permit.update_parkkihubi_permit()
            send_permit_email(
                PermitEmailType.ENDED, ParkingPermit.objects.get(id=permit.id)
            )
            ParkingPermitEventFactory.make_end_permit_event(
                permit, created_by=self.customer.user
            )

        # Delete all the draft permit while ending the customer valid permits
        draft_permits = self.customer_permit_query.filter(status=DRAFT)
        OrderItem.objects.filter(permit__in=draft_permits).delete()
        draft_permits.delete()
        logger.info("Permits ended successfully")
        return True

    def _get_address_apartments(self, address: Address):
        customer = self.customer
        if address == customer.primary_address:
            return (
                customer.primary_address_apartment,
                customer.primary_address_apartment_sv,
            )
        else:
            return customer.other_address_apartment, customer.other_address_apartment_sv

    def _update_fields_to_all_draft(self, data):
        permits = self.customer_permit_query.filter(status=DRAFT).all()
        return [self._update_permit(permit, data) for permit in permits]

    def _update_permit(self, permit: ParkingPermit, data: dict):
        keys = data.keys()
        permit_differ = ModelDiffer.start(permit, fields=EventFields.PERMIT)
        for key in keys:
            if isinstance(data[key], str) and key in ["start_time", "end_time"]:
                val = isoparse(data[key])
            else:
                val = data[key]
            setattr(permit, key, val)
        permit.save(update_fields=keys)
        permit_diff = permit_differ.stop()

        # Only create an event if the permit is not a draft
        if permit.status != DRAFT:
            ParkingPermitEventFactory.make_update_permit_event(
                permit, created_by=self.customer.user, changes=permit_diff
            )

        return permit

    def _calculate_prices(self, permit, product_with_qty):
        product = product_with_qty[0]
        quantity = product_with_qty[1]

        base_price = product.unit_price

        if not permit.primary_vehicle:
            increase = decimal.Decimal(SECONDARY_VEHICLE_PRICE_INCREASE) / 100
            base_price += increase * base_price

        discount_price = base_price - (product.low_emission_discount * base_price)
        unit_price = discount_price if permit.vehicle.is_low_emission else base_price

        product.base_price = base_price
        product.discount_price = discount_price

        product.unit_price = unit_price
        product.quantity = quantity
        product.total_price = unit_price * quantity

        return product

    def _can_buy_permit_for_address(self, address_id):
        if not self._is_valid_user_address(address_id):
            raise InvalidUserAddress(_("Invalid user address."))

        max_allowed_permit = settings.MAX_ALLOWED_USER_PERMIT

        # User can not exceed max allowed permit per user
        if self.customer_permit_query.count() > max_allowed_permit:
            raise PermitLimitExceeded(
                _("You can have a max of %(max_allowed_permit)s permits.")
                % {"max_allowed_permit": max_allowed_permit}
            )

        # If user has existing permit that is in valid or processing state then
        # the zone id from it should be used as he can have multiple permit for
        # multiple zone.
        if self.customer_permit_query.count():
            primary, secondary = self._get_primary_and_secondary_permit()
            if primary.address_id != address_id and primary.status != DRAFT:
                raise InvalidUserAddress(
                    _("You can buy permit only for address %(primary_address)s.")
                    % {"primary_address": primary.address}
                )

        return True

    def _is_valid_user_address(self, address_id):
        primary = self.customer.primary_address
        other = self.customer.other_address

        # Check if zone belongs to either of the user address zone
        if primary and primary.id == address_id:
            return True
        if other and other.id == address_id:
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

    def _get_permit(self, permit_id) -> typing.Tuple[ParkingPermit, bool]:
        permit = self.customer_permit_query.get(id=permit_id)
        return permit, permit.primary_vehicle

    def _toggle_primary_permit(self) -> typing.List[ParkingPermit]:
        primary, secondary = self._get_primary_and_secondary_permit()
        if not secondary:
            return [primary]
        primary.primary_vehicle = secondary.primary_vehicle

        update_fields = ["primary_vehicle"]
        primary.end_time = get_end_time(primary.start_time, 1)
        secondary.end_time = get_end_time(primary.start_time, 1)
        primary.month_count = 1
        secondary.month_count = 1
        update_fields.append("end_time")
        update_fields.append("month_count")

        primary.save(update_fields=update_fields)
        secondary.primary_vehicle = not secondary.primary_vehicle
        secondary.save(update_fields=update_fields)
        return [primary, secondary]

    # Start time will be next day by default if the type is immediately
    # but if the start type is FROM then the start time can not be
    # now or in the past also it can not be more than two weeks in future.
    def _get_start_type_and_start_time(self, data):
        start_time = data.get("start_time", None)
        is_start_time = bool(start_time)

        start_type = data.get("start_type", None)

        if not start_type:
            start_type = FROM if is_start_time else IMMEDIATELY

        start_time = start_time or next_day()

        if isinstance(start_time, str):
            start_time = tz.localtime(parse(start_time))

        if start_type == FROM:
            start_time = (
                two_week_from_now()
                if start_time.date() > two_week_from_now().date()
                else start_time
            )

        try:
            month_count = int(data.get("month_count", 1))
        except ValueError:
            month_count = 1

        return {
            "start_type": start_type,
            "start_time": start_time,
            "end_time": get_end_time(start_time, diff_months=month_count),
        }

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
