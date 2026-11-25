import decimal
import logging
from copy import copy

from dateutil.parser import isoparse, parse
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _

from .constants import SECONDARY_VEHICLE_PRICE_INCREASE, EventFields
from .exceptions import (
    DuplicatePermitError,
    InvalidContractTypeError,
    InvalidUserAddressError,
    NonDraftPermitUpdateError,
    PermitCanNotBeDeletedError,
    PermitCanNotBeExtendedError,
    PermitLimitExceededError,
    TemporaryVehicleValidationError,
    TraficomFetchVehicleError,
)
from .models import Address, Customer, Order, OrderItem, ParkingPermit, Vehicle
from .models.order import (
    OrderPaymentType,
    OrderStatus,
    OrderType,
    SubscriptionCancelReason,
)
from .models.parking_permit import (
    ContractType,
    ParkingPermitEndType,
    ParkingPermitEventFactory,
    ParkingPermitStartType,
    ParkingPermitStatus,
)
from .models.vehicle import VehiclePowerType, VehicleUser
from .permit_rules import CONTRACT_TYPE_MISMATCH, get_secondary_end_time
from .resolver_utils import end_permits
from .services.mail import PermitEmailType, send_permit_email
from .services.parkkihubi import sync_with_parkkihubi
from .services.traficom import Traficom
from .utils import ModelDiffer, get_end_time

logger = logging.getLogger("db")

IMMEDIATELY = ParkingPermitStartType.IMMEDIATELY
OPEN_ENDED = ContractType.OPEN_ENDED
DRAFT = ParkingPermitStatus.DRAFT
PRELIMINARY = ParkingPermitStatus.PRELIMINARY
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
        self.customer_permit_query = self.customer.permits.current()

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
            raise PermitCanNotBeExtendedError(_("You cannot extend this permit."))

        permit.validate_extension(month_count)

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

    def add_temporary_vehicle(
        self,
        permit_id,
        registration,
        start_time,
        end_time,
        *,
        user=None,
        check_limit=True,
        check_driving_licence=True,
        use_placeholder_vehicle_on_fetch_error=False,
    ):
        """Add a temporary vehicle to one of the customer's active permits.

        Defaults match the webshop flow. Admin UI disables the limit and driving
        licence checks and falls back to a placeholder vehicle if Traficom fails.
        """
        registration = registration.upper().strip()
        # Only the customer's own active permits block the vehicle; other
        # customers' permits are allowed.
        has_valid_permit = self.customer_permit_query.filter(
            vehicle__registration_number__iexact=registration,
        ).exists()

        if has_valid_permit:
            raise TemporaryVehicleValidationError(
                _("There's already a valid permit for a given vehicle.")
            )

        permit, _primary_vehicle = self._get_permit(permit_id)
        start_time, end_time = permit.parse_temporary_vehicle_times(
            start_time, end_time
        )

        vehicle = self._fetch_temporary_vehicle(
            registration,
            use_placeholder_on_error=use_placeholder_vehicle_on_fetch_error,
        )

        if (
            check_driving_licence
            and not self.customer.has_valid_driving_licence_for_vehicle(vehicle)
        ):
            raise TraficomFetchVehicleError(
                _("Customer does not have a valid driving licence for this vehicle")
            )

        permit.add_temporary_vehicle(
            user or self.customer.user,
            vehicle,
            start_time,
            end_time,
            check_limit=check_limit,
        )

        sync_with_parkkihubi(permit)

        send_permit_email(PermitEmailType.TEMP_VEHICLE_ACTIVATED, permit)
        return True

    def _fetch_temporary_vehicle(self, registration, *, use_placeholder_on_error):
        try:
            return Traficom().fetch_vehicle_details(registration_number=registration)
        except TraficomFetchVehicleError:
            if not use_placeholder_on_error:
                raise

        power_type, _created = VehiclePowerType.objects.get_or_create(
            identifier="01",
            defaults={"name": "Bensin"},
        )
        vehicle, created = Vehicle.objects.get_or_create(
            registration_number=registration,
            defaults={"power_type": power_type},
        )
        if created:
            vehicle_user, _created = VehicleUser.objects.get_or_create(
                national_id_number=self.customer.national_id_number
            )
            vehicle.users.set([vehicle_user])
        return vehicle

    def remove_temporary_vehicle(self, permit_id):
        permit_details = self._get_permit(permit_id)
        permit = permit_details[0]
        permit.remove_temporary_vehicle()
        sync_with_parkkihubi(permit)
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
            if permit.status == PAYMENT_IN_PROGRESS:
                self._cancel_timed_out_payment(permit)
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

            if permit.has_address_changed:
                address_id = permit.address.pk if permit.address else None
                logger.info(
                    f"Permit {permit.pk} address_id={address_id} does not "
                    f"match with customer's primary or other address. "
                    f"Marking permit to end at the end of the day."
                )
                permit.address_changed = True
                permit.address_changed_date = tz.localdate()
                permit.save()

            permits.append(permit)
        return permits

    @transaction.atomic
    def _cancel_timed_out_payment(self, permit):
        latest_order = permit.latest_order
        if latest_order is None:
            return

        # Match PaymentView's lock order, then discard the stale permit state.
        order = Order.objects.select_for_update().get(pk=latest_order.pk)
        permit.refresh_from_db(from_queryset=ParkingPermit.objects.select_for_update())
        if (
            permit.status != PAYMENT_IN_PROGRESS
            or permit.latest_order != order
            or order.status != OrderStatus.DRAFT
            or order.paid_time is not None
            or order.payment_processed_at is not None
            or order.talpa_last_valid_purchase_time is None
        ):
            return

        deadline = order.talpa_last_valid_purchase_time + tz.timedelta(
            minutes=settings.TALPA_ORDER_PAYMENT_WEBHOOK_WAIT_BUFFER_MINS
        )
        if deadline >= tz.now():
            return

        # Extension orders never put the permit into PAYMENT_IN_PROGRESS.
        order.status = OrderStatus.CANCELLED
        order.save(update_fields=["status", "modified_at"])
        permit.status = CANCELLED
        permit.save(update_fields=["status", "modified_at"])

    @transaction.atomic
    def create(self, address_id, registration):
        Customer.objects.select_for_update(no_key=True).get(pk=self.customer.pk)
        if self.customer_permit_query.filter(
            vehicle__registration_number=registration
        ).exists():
            raise DuplicatePermitError(_("Permit for a given vehicle already exist."))
        address = Address.objects.get(id=address_id)
        if self._can_buy_permit_for_address(address.id, creating=True):
            contract_type = OPEN_ENDED
            primary_vehicle = True
            primary_permit = None
            if self.customer_permit_query.count():
                primary_permit = self.customer_permit_query.get(primary_vehicle=True)
                contract_type = primary_permit.contract_type
                primary_vehicle = not primary_permit.primary_vehicle

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

            start_time = (
                max(tz.now(), primary_permit.start_time) if primary_permit else tz.now()
            )
            end_time = get_secondary_end_time(start_time, 1, primary_permit)

            address_apartment, address_apartment_sv = self._get_address_apartments(
                address
            )
            permit = ParkingPermit(
                customer=self.customer,
                address=address,
                address_apartment=address_apartment,
                address_apartment_sv=address_apartment_sv,
                parking_zone=address.zone,
                primary_vehicle=primary_vehicle,
                contract_type=contract_type,
                start_time=start_time,
                end_time=end_time,
                vehicle=vehicle,
            )

            permit.validate_purchase(primary_permit)
            permit.save()

            ParkingPermitEventFactory.make_create_permit_event(
                permit, created_by=self.customer.user
            )

            return permit

    def delete(self, permit_id):
        permit = ParkingPermit.objects.get(customer=self.customer, id=permit_id)
        if permit.status not in [DRAFT, PRELIMINARY]:
            raise PermitCanNotBeDeletedError(_("Non draft permit can not be deleted"))
        OrderItem.objects.filter(permit=permit).delete()
        permit.delete()

        if self.customer_permit_query.count():
            other_permit = self.customer_permit_query.first()
            data = {"primary_vehicle": True}
            self._update_permit(other_permit, data)
        return True

    @transaction.atomic
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

        if {"start_type", "start_time", "contract_type", "month_count"} & keys:
            Customer.objects.select_for_update(no_key=True).get(pk=self.customer.pk)
            targets = (
                [self._get_permit(permit_id)[0]]
                if permit_id
                else list(
                    self.customer_permit_query.filter(status__in=[DRAFT, PRELIMINARY])
                )
            )
            if {"contract_type", "month_count"} & keys and not data.get(
                "contract_type"
            ):
                raise InvalidContractTypeError(_("Contract type is required"))
            start_changes = (
                self._get_start_type_and_start_time(data)
                if "start_type" in keys or "start_time" in keys
                else {}
            )
            candidates = []
            for permit in targets:
                if permit.status not in [DRAFT, PRELIMINARY]:
                    raise NonDraftPermitUpdateError(
                        _("This is not a draft permit and can not be edited")
                    )
                candidate = copy(permit)
                changes = dict(fields_to_update)
                changes.update(start_changes)
                contract_type = data.get("contract_type", permit.contract_type)
                # A new date starts a fresh duration selection. Keep an explicit
                # duration for callers submitting the entire period together.
                month_count = data.get(
                    "month_count", 1 if start_changes else permit.month_count
                )
                if candidate.primary_vehicle:
                    month_count = self._get_month_count_for_primary_permit(
                        contract_type, month_count
                    )
                elif contract_type == OPEN_ENDED:
                    month_count = 1
                changes.update(contract_type=contract_type, month_count=month_count)
                for key, value in changes.items():
                    setattr(candidate, key, value)
                changes["end_time"] = get_end_time(candidate.start_time, month_count)
                candidate.end_time = changes["end_time"]
                candidates.append((permit, candidate, changes))

            pair = {p.pk: p for p in self.customer_permit_query.all()}
            pair.update({candidate.pk: candidate for _, candidate, _ in candidates})
            if len({p.contract_type for p in pair.values()}) > 1:
                raise InvalidContractTypeError(CONTRACT_TYPE_MISMATCH)
            primary = next((p for p in pair.values() if p.primary_vehicle), None)
            for _original, candidate, changes in candidates:
                if not candidate.primary_vehicle:
                    candidate.end_time = get_secondary_end_time(
                        candidate.start_time, candidate.month_count, primary
                    )
                    changes["end_time"] = candidate.end_time
            for candidate in pair.values():
                if not candidate.primary_vehicle:
                    candidate.validate_purchase(primary)
            return [
                self._update_permit(permit, changes)
                for permit, _, changes in candidates
            ]

        return self._update_fields_to_all_draft(fields_to_update)

    @transaction.atomic
    def end(
        self,
        permit_ids,
        end_type,
        iban=None,
        user=None,
        subscription_cancel_reason=SubscriptionCancelReason.USER_CANCELLED,
        cancel_from_talpa=True,
        ignore_talpa_errors=False,
        force_end=False,
    ):
        logger.info(
            f"Ending permits: {','.join([str(permit_id) for permit_id in permit_ids])}"
        )
        Customer.objects.select_for_update(no_key=True).get(pk=self.customer.pk)
        permits = list(
            self.customer_permit_query.filter(id__in=permit_ids).order_by(
                "primary_vehicle"
            )
        )
        # Each subscription ends on its own billing date in a joint cancellation.
        ending_both_subscriptions = (
            end_type == ParkingPermitEndType.AFTER_CURRENT_PERIOD
            and len(permits) == 2
            and all(permit.is_open_ended for permit in permits)
            and not self.customer.active_permits.exclude(id__in=permit_ids).exists()
        )

        end_permits(
            user,
            *permits,
            end_type=end_type,
            iban=iban,
            subscription_cancel_reason=subscription_cancel_reason,
            cancel_from_talpa=cancel_from_talpa,
            ignore_talpa_errors=ignore_talpa_errors,
            force_end=force_end or ending_both_subscriptions,
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
        permits = self.customer_permit_query.filter(
            status__in=[DRAFT, PRELIMINARY]
        ).all()
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

    def _can_buy_permit_for_address(self, address_id, *, creating=False):
        if not self._is_valid_user_address(address_id):
            raise InvalidUserAddressError(_("Invalid user address."))

        count = self.customer_permit_query.count()
        limit = settings.MAX_ALLOWED_USER_PERMIT
        if count > limit or (
            creating
            and count == limit
            and self.customer_permit_query.open_ended().exists()
        ):
            raise PermitLimitExceededError(
                _("You can have a max of %(max_allowed_permit)s permits.")
                % {"max_allowed_permit": limit}
            )

        # If user has existing permit that is in valid or processing state then
        # the zone id from it should be used as he can have multiple permit for
        # multiple zone.
        if count:
            primary, secondary = self._get_primary_and_secondary_permit()
            if primary.address_id != address_id and primary.status != DRAFT:
                raise InvalidUserAddressError(
                    _("You can buy permit only for address %(primary_address)s.")
                    % {"primary_address": primary.address}
                )

        return True

    def _is_valid_user_address(self, address_id):
        primary = self.customer.primary_address
        other = self.customer.other_address

        # Check if the address is primary or other address of the user
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

    def _get_permit(self, permit_id) -> tuple[ParkingPermit, bool]:
        permit = self.customer_permit_query.get(id=permit_id)
        return permit, permit.primary_vehicle

    def _toggle_primary_permit(self) -> list[ParkingPermit]:
        primary, secondary = self._get_primary_and_secondary_permit()
        if not secondary:
            return [primary]
        primary.primary_vehicle = secondary.primary_vehicle

        if primary.status not in [DRAFT, PRELIMINARY] or secondary.status not in [
            DRAFT,
            PRELIMINARY,
        ]:
            raise NonDraftPermitUpdateError(
                _("This is not a draft permit and can not be edited")
            )
        primary.start_time = secondary.start_time = max(
            primary.start_time, secondary.start_time
        )
        update_fields = ["primary_vehicle", "start_time"]
        primary.end_time = get_end_time(primary.start_time, 1)
        secondary.end_time = get_end_time(secondary.start_time, 1)
        primary.month_count = 1
        secondary.month_count = 1
        update_fields.append("end_time")
        update_fields.append("month_count")

        secondary.primary_vehicle = not secondary.primary_vehicle
        primary.validate_purchase(secondary)
        primary.save(update_fields=update_fields)
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

    def _get_month_count_for_primary_permit(self, contract_type, month_count):
        if contract_type == OPEN_ENDED:
            return 1
        if month_count > 12:
            return 12
        if month_count < 1:
            return 1
        return month_count
