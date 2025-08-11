import itertools
import logging
import operator
from datetime import datetime
from decimal import Decimal
from typing import Tuple

from dateutil.parser import isoparse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.postgres.fields import DateTimeRangeField
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from helsinki_gdpr.models import SerializableMixin

from ..exceptions import (
    DuplicatePermit,
    PermitCanNotBeEnded,
    TemporaryVehicleValidationError,
)
from ..utils import (
    calc_net_price,
    calc_vat_price,
    diff_months_ceil,
    diff_months_floor,
    end_date_to_datetime,
    flatten_dict,
    get_end_time,
    get_permit_prices,
    increment_end_time,
    round_up,
)
from .mixins import TimestampedModelMixin, UserStampedModelMixin
from .parking_zone import ParkingZone
from .temporary_vehicle import TemporaryVehicle
from .vehicle import Vehicle

logger = logging.getLogger("db")


class ParkingPermitType(models.TextChoices):
    RESIDENT = "RESIDENT", _("Resident permit")
    COMPANY = "COMPANY", _("Company permit")


class ContractType(models.TextChoices):
    FIXED_PERIOD = "FIXED_PERIOD", _("Fixed period")
    OPEN_ENDED = "OPEN_ENDED", _("Open ended")


class ParkingPermitStartType(models.TextChoices):
    IMMEDIATELY = "IMMEDIATELY", _("Immediately")
    FROM = "FROM", _("From")


class ParkingPermitEndType(models.TextChoices):
    IMMEDIATELY = "IMMEDIATELY", _("Immediately")
    AFTER_CURRENT_PERIOD = "AFTER_CURRENT_PERIOD", _("After current period")
    PREVIOUS_DAY_END = "PREVIOUS_DAY_END", _("Previous day end")


class ParkingPermitStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    PRELIMINARY = "PRELIMINARY", _("Preliminary")
    PAYMENT_IN_PROGRESS = "PAYMENT_IN_PROGRESS", _("Payment in progress")
    VALID = "VALID", _("Valid")
    CANCELLED = "CANCELLED", _("Cancelled")
    CLOSED = "CLOSED", _("Closed")


MAX_MONTHS = 12


class ParkingPermitQuerySet(models.QuerySet):
    def fixed_period(self):
        return self.filter(contract_type=ContractType.FIXED_PERIOD)

    def open_ended(self):
        return self.filter(contract_type=ContractType.OPEN_ENDED)

    def active(self):
        active_status = [
            ParkingPermitStatus.VALID,
            ParkingPermitStatus.PAYMENT_IN_PROGRESS,
        ]
        return self.filter(status__in=active_status)

    def active_after(self, time):
        return self.active().filter(Q(end_time__isnull=True) | Q(end_time__gt=time))


class ParkingPermitManager(SerializableMixin.SerializableManager):
    pass


class ParkingPermit(SerializableMixin, TimestampedModelMixin):
    customer = models.ForeignKey(
        "Customer",
        verbose_name=_("Customer"),
        on_delete=models.PROTECT,
        related_name="permits",
    )
    vehicle = models.ForeignKey(
        Vehicle,
        verbose_name=_("Vehicle"),
        on_delete=models.PROTECT,
        related_name="permits",
    )
    next_vehicle = models.ForeignKey(
        Vehicle,
        verbose_name=_("Next vehicle"),
        on_delete=models.PROTECT,
        related_name="next_permits",
        blank=True,
        null=True,
    )
    temp_vehicles = models.ManyToManyField(TemporaryVehicle, blank=True)
    parking_zone = models.ForeignKey(
        ParkingZone,
        verbose_name=_("Parking zone"),
        on_delete=models.PROTECT,
        related_name="permits",
    )
    next_parking_zone = models.ForeignKey(
        ParkingZone,
        verbose_name=_("Next parking zone"),
        on_delete=models.PROTECT,
        related_name="next_permits",
        blank=True,
        null=True,
    )
    type = models.CharField(
        _("Type"),
        max_length=32,
        choices=ParkingPermitType.choices,
        default=ParkingPermitType.RESIDENT,
    )
    status = models.CharField(
        _("Status"),
        max_length=32,
        choices=ParkingPermitStatus.choices,
        default=ParkingPermitStatus.DRAFT,
    )
    start_time = models.DateTimeField(_("Start time"), default=timezone.now)
    end_time = models.DateTimeField(_("End time"), blank=True, null=True)
    primary_vehicle = models.BooleanField(default=True)
    synced_with_parkkihubi = models.BooleanField(default=False)
    bypass_traficom_validation = models.BooleanField(
        verbose_name=_("Bypass Traficom validation"),
        default=False,
    )
    vehicle_changed = models.BooleanField(default=False)
    vehicle_changed_date = models.DateField(
        _("Vehicle changed date"), null=True, blank=True
    )
    address_changed = models.BooleanField(default=False)
    address_changed_date = models.DateField(
        _("Address changed date"), null=True, blank=True
    )
    contract_type = models.CharField(
        _("Contract type"),
        max_length=16,
        choices=ContractType.choices,
        default=ContractType.OPEN_ENDED,
    )
    start_type = models.CharField(
        _("Start type"),
        max_length=16,
        choices=ParkingPermitStartType.choices,
        default=ParkingPermitStartType.IMMEDIATELY,
    )
    end_type = models.CharField(
        _("End type"),
        max_length=32,
        choices=ParkingPermitEndType.choices,
        default=ParkingPermitStartType.IMMEDIATELY,
    )
    month_count = models.IntegerField(_("Month count"), default=1)
    description = models.TextField(_("Description"), blank=True)
    address = models.ForeignKey(
        "Address",
        verbose_name=_("Address"),
        on_delete=models.PROTECT,
        related_name="permits",
        null=True,
        blank=True,
    )
    address_apartment = models.CharField(
        _("Address apartment"), max_length=32, blank=True, null=True
    )
    address_apartment_sv = models.CharField(
        _("Address apartment (sv)"), max_length=32, blank=True, null=True
    )
    next_address = models.ForeignKey(
        "Address",
        verbose_name=_("Next address"),
        on_delete=models.PROTECT,
        related_name="next_permits",
        null=True,
        blank=True,
    )
    next_address_apartment = models.CharField(
        _("Next address apartment"), max_length=32, blank=True, null=True
    )
    next_address_apartment_sv = models.CharField(
        _("Next address apartment (sv)"), max_length=32, blank=True, null=True
    )

    serialize_fields = (
        {"name": "id"},
        {"name": "vehicle", "accessor": lambda v: str(v)},
        {"name": "status"},
        {"name": "contract_type"},
        {"name": "start_type"},
        {"name": "start_time"},
        {"name": "end_time"},
        {"name": "month_count"},
        {"name": "description"},
    )

    objects = ParkingPermitManager.from_queryset(ParkingPermitQuerySet)()

    class Meta:
        ordering = ["-id"]
        verbose_name = _("Parking permit")
        verbose_name_plural = _("Parking permits")

    def __str__(self):
        return str(self.id)

    @property
    def full_address(self):
        return (
            f"{self.address.street_name} {self.address.street_number} "
            f"{self.address_apartment}, "
            f"{self.address.postal_code} {self.address.city}"
            if self.address
            else ""
        )

    @property
    def full_address_sv(self):
        return (
            f"{self.address.street_name_sv} {self.address.street_number} "
            f"{self.address_apartment_sv}, "
            f"{self.address.postal_code} {self.address.city_sv}"
            if self.address
            else ""
        )

    @property
    def full_next_address(self):
        return (
            f"{self.next_address.street_name} {self.next_address.street_number} "
            f"{self.next_address_apartment}, "
            f"{self.next_address.postal_code} {self.next_address.city}"
            if self.next_address
            else ""
        )

    @property
    def full_next_address_sv(self):
        return (
            f"{self.next_address.street_name_sv} {self.next_address.street_number} "
            f"{self.next_address_apartment_sv}, "
            f"{self.next_address.postal_code} {self.next_address.city_sv}"
            if self.next_address
            else ""
        )

    @property
    def is_secondary_vehicle(self):
        return not self.primary_vehicle

    @property
    def temporary_vehicles(self):
        return self.temp_vehicles.all()

    @property
    def is_order_confirmed(self):
        from .order import OrderStatus

        if self.orders:
            recent_order = self.orders.order_by("-paid_time").first()
            return (
                recent_order.status == OrderStatus.CONFIRMED if recent_order else False
            )
        return False

    @property
    def active_temporary_vehicle(self):
        """Get the active temporary vehicle for the permit"""
        return (
            self.temporary_vehicles.filter(
                is_active=True,
            )
            .select_related("vehicle")
            .first()
        )

    @property
    def consent_low_emission_accepted(self):
        return self.vehicle.consent_low_emission_accepted

    @property
    def latest_order(self):
        """Get the latest order for the permit

        Multiple orders can be created for the same permit
        when, for example, the vehicle or the address of
        the permit is changed.

        If extension request order, returns that order instead
        """
        if order := self.latest_extension_request_order:
            return order

        return self.orders.latest("id") if self.orders.exists() else None

    @property
    def talpa_order_id(self):
        if self.latest_order and self.latest_order.talpa_order_id:
            return self.latest_order.talpa_order_id
        return None

    @property
    def receipt_url(self):
        if self.latest_order and self.latest_order.talpa_receipt_url:
            return self.latest_order.talpa_receipt_url
        return None

    @property
    def update_card_url(self):
        if self.latest_order and self.latest_order.talpa_update_card_url:
            return self.latest_order.talpa_update_card_url
        return None

    @property
    def checkout_url(self):
        if self.latest_order and self.latest_order.talpa_checkout_url:
            return self.latest_order.talpa_checkout_url
        return None

    @property
    def latest_extension_request_order(self):
        if ext_request := self.permit_extension_requests.select_related(
            "order"
        ).first():
            return ext_request.order
        return None

    @property
    def latest_order_items(self):
        """Get latest order items for the permit"""
        return self.order_items.filter(order=self.latest_order)

    @property
    def latest_order_item(self):
        return self.latest_order_items.first()

    @property
    def permit_prices(self):
        if self.is_fixed_period:
            end_time = self.end_time
        else:
            end_time = get_end_time(self.start_time, 1)
        return get_permit_prices(
            self.parking_zone,
            self.vehicle.is_low_emission,
            not self.primary_vehicle,
            self.start_time.date(),
            end_time.date(),
        )

    @property
    def is_valid(self):
        return self.status == ParkingPermitStatus.VALID

    @property
    def is_closed(self):
        return self.status == ParkingPermitStatus.CLOSED

    @property
    def is_open_ended(self):
        return self.contract_type == ContractType.OPEN_ENDED

    @property
    def is_fixed_period(self):
        return self.contract_type == ContractType.FIXED_PERIOD

    @property
    def can_end_immediately(self):
        now = timezone.now()
        return self.is_valid and (self.end_time is None or now < self.end_time)

    @property
    def can_end_after_current_period(self):
        if not self.is_valid:
            return False

        if self.end_time is None:
            return False

        if self.has_address_changed:
            return False

        return timezone.localdate(self.current_period_end_time) <= timezone.localdate(
            self.end_time
        )

    @property
    def months_used(self):
        now = timezone.now()
        diff_months = diff_months_ceil(self.start_time, now)
        if self.is_fixed_period:
            # self.month_count acts as an upper bound for diff_months
            # which ensures nonnegative months_left
            return min(self.month_count, diff_months)
        return diff_months

    @property
    def months_left(self):
        if self.is_open_ended:
            # if the open-ended permit is not yet started, return 1
            return 1 if self.start_time > timezone.now() else None
        return self.month_count - self.months_used

    @property
    def current_period_start_time(self):
        if self.is_open_ended:
            return self.start_time
        return self.start_time + relativedelta(months=self.months_used - 1)

    @property
    def current_period_end_time(self):
        if self.is_open_ended:
            # If open-ended permit is already renewed for the new period,
            # then use previous period end time
            now = timezone.now()
            if self.end_time and self.end_time - relativedelta(months=1) > now:
                return self.end_time - relativedelta(months=1)
            return self.end_time
        return self.current_period_end_time_with_fixed_months(self.months_used)

    @property
    def current_period_range(self):

        # Workaround for invalid ranges in ParkingPermitEvent.validity_period
        # NOTE:
        # - permit end time is allowed to be None for historical reasons,
        # but this _shouldn't_ happen.
        # (Possible TODO: properly enforce this by migrating the field
        # to not allow null values. Note that this may end up being difficult
        # due to historical data and the need to adjust
        # ParkingPermitEvent.validity_period end dates etc.)
        # - this property is only used by some ParkingPermitEvent-creator
        # methods (eg. make_update_permit_event())
        # to set the validity_period-field in ParkingPermitEvent-model
        # - validity_period is a DateTimeRangeField which raises an error
        # if a save is attempted with non-null start time and null end time.
        # (Or vice versa, but start time can't be null.)
        # - we avoid this error by returning None here
        if self.end_time is None:
            return None

        return self.start_time, self.end_time

    @property
    def next_period_start_time(self):
        return self.start_time + relativedelta(months=self.months_used)

    @property
    def can_be_refunded(self):
        """Determines if a permit is refundable in principle. The exact amounts refunded
        may still be zero depending on individual refundable order amounts."""

        # only valid permits can be refunded
        if not self.is_valid:
            return False

        # any fixed period permit
        if self.is_fixed_period:
            return True

        now = timezone.now()

        # if open ended permit has not yet started
        if self.current_period_start_time > now:
            return True

        # if the end period > 1 month: this can happen if Talpa renews permit
        if self.end_time and self.end_time - relativedelta(months=1) > now:
            return True

        return False

    @property
    def total_refund_amount(self):
        data_per_vat = self.get_vat_based_refund_amounts_for_unused_items()
        return sum(vat_data["total"] for vat_data in data_per_vat.values())

    @property
    def has_address_changed(self):
        customer_addresses = [
            self.customer.primary_address,
            self.customer.other_address,
        ]
        if not self.address and not customer_addresses:
            return False
        # check if the permit address still belongs to the customer
        return self.address not in customer_addresses

    @property
    def max_extension_month_count(self):
        """Returns the maximum number of months you can extend the permit.

        For a primary vehicle, this is up to 12.

        For a secondary vehicle, this is the end date of the primary vehicle,
        not counting any value less than one month (if month count less than 1,
        then it should not be logically possible to extend the permit).
        """
        if self.primary_vehicle:
            return MAX_MONTHS

        if (
            primary_permit := self._meta.default_manager.filter(
                status=ParkingPermitStatus.VALID,
                customer=self.customer,
                primary_vehicle=True,
            )
            .exclude(pk=self.pk)
            .first()
        ):
            return max(
                diff_months_floor(
                    timezone.localtime(self.current_period_end_time),
                    timezone.localtime(primary_permit.end_time),
                ),
                0,
            )

        return MAX_MONTHS

    @property
    def can_extend_permit(self):
        """Checks if permit can be extended:
        1. Must be a valid fixed period permit.
        2. Cannot have any pending requests.
        3. Must be within 14 days of end time.
        4. PERMIT_EXTENSIONS_ENABLED flag is True.
        """
        return self._can_extend_parking_permit(is_date_restriction=True)

    @property
    def can_admin_extend_permit(self):
        """Checks if permit can be extended:
        1. Must be a valid fixed period permit.
        2. Cannot have any pending requests.
        3. PERMIT_EXTENSIONS_ENABLED flag is True.
        """
        return self._can_extend_parking_permit(is_date_restriction=False)

    def save(self, *args, **kwargs):
        # Enforce unique customer-vehicle-pair depending on the status,
        # duplicate customer-vehicle-pairs are allowed only for
        # permits with cancelled/closed status
        non_duplicable_statuses = [
            ParkingPermitStatus.VALID,
            ParkingPermitStatus.PAYMENT_IN_PROGRESS,
            ParkingPermitStatus.DRAFT,
            ParkingPermitStatus.PRELIMINARY,
        ]

        duplicate_query = ParkingPermit.objects.exclude(id=self.id).filter(
            customer_id=self.customer_id,
            vehicle__registration_number=self.vehicle.registration_number,
            # Pre-existing cancelled/closed permits do not contribute
            # towards potential duplicates
            status__in=non_duplicable_statuses,
        )

        # If the permit being saved is cancelled/closed, we can
        # short-circuit to avoid db-hit/query-evaluation
        # as those statuses will never break the constraint
        check_for_duplicates = self.status in non_duplicable_statuses
        if check_for_duplicates and duplicate_query.exists():
            raise DuplicatePermit(_("Permit for a given vehicle already exist."))

        return super().save(*args, **kwargs)

    def _can_extend_parking_permit(self, *, is_date_restriction=True):
        if not all(
            (
                settings.PERMIT_EXTENSIONS_ENABLED,
                self.status == ParkingPermitStatus.VALID,
                self.contract_type == ContractType.FIXED_PERIOD,
                self.end_time is not None,
            )
        ):
            return False

        if self.has_address_changed:
            return False

        if is_date_restriction and timezone.localdate(
            self.end_time
        ) > timezone.localdate(timezone.now() + relativedelta(days=14)):
            return False

        # do database op last
        return not self.has_pending_extension_request

    def get_pending_extension_requests(self):
        """Returns all PENDING extension requests."""
        return self.permit_extension_requests.pending()

    @property
    def has_pending_extension_request(self):
        """Returns True if any PENDING extension requests."""
        return self.get_pending_extension_requests().exists()

    def current_period_end_time_with_fixed_months(self, months):
        end_time = get_end_time(self.start_time, months)
        return max(self.start_time, end_time)

    def get_price_list_for_extended_permit(self, month_count):
        """Returns price list when purchasing additional months on
        a fixed-period permit.

        Each item consists of:

        "product": product instance
        "start_date": start of period
        "end_date": end of period
        "vat": VAT rate
        "price": gross price
        "net_price": net price
        "vat_price": VAT price
        """
        is_secondary = not self.primary_vehicle
        is_low_emission = self.vehicle.is_low_emission

        for product, grouper in itertools.groupby(
            self.get_future_product_month_dates(month_count),
            operator.itemgetter("product"),
        ):
            items = list(grouper)

            start_date = min([item["start_date"] for item in items])
            end_date = max([item["end_date"] for item in items])

            price = product.get_modified_unit_price(is_low_emission, is_secondary)

            month_count = len(items)
            total_price = price * month_count

            net_price = round_up(calc_net_price(total_price, product.vat))
            vat_price = round_up(calc_vat_price(total_price, product.vat))

            yield {
                "product": product,
                "month_count": month_count,
                "vat": product.vat,
                "start_date": start_date,
                "end_date": end_date,
                "price": total_price,
                "unit_price": price,
                "net_price": net_price,
                "vat_price": vat_price,
            }

    def get_future_product_month_dates(self, month_count):
        """Break down of future start/end times per month from the
        period after the current end of the permit until the number of months."""

        from_date = self.end_time.replace(hour=0, minute=0, second=0) + relativedelta(
            days=1
        )

        start_date = timezone.localdate(from_date)
        end_date = timezone.localdate(get_end_time(from_date, month_count))

        products = (
            self.parking_zone.products.for_resident()
            .for_date_range(start_date, end_date)
            .order_by("start_date")
            .iterator()
        )
        # calculate the price change list in the affected date range
        product = next(products, None)

        # for each product in our range, find the start and end dates
        # of whole months within that range
        # add hard limit that more products can't be returned than there is months
        loop_count = 0
        while product and start_date < end_date and loop_count < month_count:
            yield {
                "product": product,
                "start_date": start_date,
                "end_date": start_date + relativedelta(months=1, days=-1),
            }
            start_date += relativedelta(months=1)
            loop_count += 1

            if start_date > product.end_date:
                product = next(products, None)

    def get_price_change_list(self, new_zone, is_low_emission):
        """Get a list of price changes if the permit is changed

        Only vehicle and zone change will affect the price

        Args:
            new_zone: new zone used in the permit
            is_low_emission: True if the new vehicle is a low emission one
            month_count: number of additional months, if change in permit month count
                (fixed period only)

        Returns:
            A list of price change information
        """
        # TODO: currently, company permit type is not available
        previous_products = self.parking_zone.products.for_resident()
        new_products = new_zone.products.for_resident()
        is_secondary = not self.primary_vehicle
        if self.is_open_ended:
            start_date = timezone.localdate(self.next_period_start_time)
            end_date = start_date + relativedelta(months=1, days=-1)
            previous_product = previous_products.get_for_date(start_date)
            previous_price = previous_product.get_modified_unit_price(
                self.vehicle.is_low_emission,
                is_secondary,
            )
            new_product = new_products.get_for_date(start_date)
            new_price = new_product.get_modified_unit_price(
                is_low_emission,
                is_secondary,
            )
            diff_price = new_price - previous_price
            price_change_vat = calc_vat_price(diff_price, new_product.vat).quantize(
                Decimal("0.0001")
            )
            # if the permit ends more than a month from now, count this month
            diff_months = (
                relativedelta(timezone.localdate(self.end_time), timezone.localdate())
            ).months
            month_count = 1 if diff_months > 0 else 0

            return [
                {
                    "product": new_product.name,
                    "previous_price": previous_price,
                    "new_price": new_price,
                    "price_change_vat": price_change_vat,
                    "price_change_vat_percent": new_product.vat_percentage,
                    "price_change": diff_price,
                    "start_date": start_date,
                    "end_date": end_date,
                    "month_count": month_count,
                }
            ]

        if self.is_fixed_period:
            # price change affected date range and products
            start_date = timezone.localdate(self.next_period_start_time)
            end_date = timezone.localdate(self.end_time)
            previous_product_iter = previous_products.for_date_range(
                start_date, end_date
            ).iterator()
            new_product_iter = new_products.for_date_range(
                start_date, end_date
            ).iterator()

            # calculate the price change list in the affected date range
            month_start_date = start_date
            previous_product = next(previous_product_iter, None)
            new_product = next(new_product_iter, None)
            price_change_list = []
            while month_start_date < end_date and previous_product and new_product:
                previous_price = previous_product.get_modified_unit_price(
                    self.vehicle.is_low_emission,
                    is_secondary,
                )
                new_price = new_product.get_modified_unit_price(
                    is_low_emission,
                    is_secondary,
                )
                diff_price = new_price - previous_price
                if (
                    len(price_change_list) > 0
                    and price_change_list[-1]["product"] == new_product.name
                    and price_change_list[-1]["price_change"] == diff_price
                ):
                    # if it's the same product and diff price is the same as
                    # previous one, combine the price change by increase the
                    # quantity by 1
                    price_change_list[-1]["month_count"] += 1
                else:
                    # if the price is decreased, get VAT from the previous permit order
                    vat = (
                        self.latest_order.vat
                        if diff_price < 0 and self.latest_order
                        else new_product.vat
                    )
                    # if the product is different or diff price is different,
                    # create a new price change item
                    price_change_vat = calc_vat_price(diff_price, vat).quantize(
                        Decimal("0.0001")
                    )

                    price_change_list.append(
                        {
                            "product": new_product.name,
                            "previous_price": previous_price,
                            "new_price": new_price,
                            "price_change_vat": price_change_vat,
                            "price_change_vat_percent": vat * 100,
                            "price_change": diff_price,
                            "start_date": month_start_date,
                            "month_count": 1,
                        }
                    )

                month_start_date += relativedelta(months=1)
                if month_start_date > previous_product.end_date:
                    previous_product = next(previous_product_iter, None)
                if month_start_date > new_product.end_date:
                    new_product = next(new_product_iter, None)

            # calculate the end date based on month count in
            # each price change item
            for price_change in price_change_list:
                price_change["end_date"] = price_change["start_date"] + relativedelta(
                    months=price_change["month_count"], days=-1
                )
            return price_change_list

    def end_permit(self, end_type, force_end=False):
        self.end_type = end_type
        if end_type == ParkingPermitEndType.PREVIOUS_DAY_END:
            vehicle_changed_date = self.vehicle_changed_date
            if vehicle_changed_date:
                end_time = end_date_to_datetime(vehicle_changed_date)
            else:
                previous_day = timezone.localtime() - timezone.timedelta(days=1)
                end_time = previous_day.replace(
                    hour=23,
                    minute=59,
                    second=59,
                    microsecond=999999,
                )
        elif end_type == ParkingPermitEndType.AFTER_CURRENT_PERIOD:
            end_time = self.current_period_end_time
        else:
            end_time = max(self.start_time, timezone.now())

        if (
            not force_end
            and self.primary_vehicle
            and self.customer.permits.active_after(end_time)
            .exclude(id=self.id)
            .exists()
        ):
            raise PermitCanNotBeEnded(
                _(
                    "Cannot close primary vehicle permit if an active secondary vehicle permit exists"
                )
            )

        self.end_time = end_time
        if (
            end_type == ParkingPermitEndType.IMMEDIATELY
            or end_type == ParkingPermitEndType.PREVIOUS_DAY_END
        ):
            self.status = ParkingPermitStatus.CLOSED
            self.temp_vehicles.update(is_active=False, end_time=end_time)

        self.cancel_extension_requests()
        self.save()

    def renew_open_ended_permit(self):
        """Add month to open-ended permit after subscription renewal"""

        if self.contract_type != ContractType.OPEN_ENDED:
            raise ValueError("This permit is not open-ended so cannot be renewed")
        self.end_time = increment_end_time(self.start_time, self.end_time, months=1)
        self.save()

    def extend_permit(self, additional_months):
        """Extends the end time of the permit by given months."""

        self.month_count += additional_months
        self.end_time = get_end_time(self.start_time, self.month_count)
        self.save()

    def cancel_extension_requests(self):
        self.permit_extension_requests.cancel_pending()

    def get_vat_based_refund_amounts_for_unused_items(self):
        totals_per_vat = {}
        if not self.can_be_refunded:
            return totals_per_vat

        unused_order_items = self.get_unused_order_items_for_all_orders()

        for order_item, quantity, date_range in unused_order_items:
            vat = order_item.vat
            if vat not in totals_per_vat:
                totals_per_vat[vat] = {
                    "total": Decimal(0),
                    "orders": set(),
                    "order_items": set(),
                }
            totals_per_vat[vat]["total"] += order_item.payment_unit_price * quantity
            totals_per_vat[vat]["orders"].add(order_item.order)
            totals_per_vat[vat]["order_items"].add(order_item)
        return totals_per_vat

    def get_total_refund_amount_for_unused_items(self):
        total = Decimal(0)
        if not self.can_be_refunded:
            return total

        unused_order_items = self.get_unused_order_items()

        for order_item, quantity, date_range in unused_order_items:
            total += order_item.payment_unit_price * quantity
        return total

    def parse_temporary_vehicle_times(
        self,
        start_time: str,
        end_time: str,
    ) -> Tuple[datetime, datetime]:
        """Returns start and and end times for a temporary vehicle, checking
        times against the permit.

        Parses input strings. If start time less than current time, should be same as
        current time. If end time less than start time + 1 hour, should be start time + 1 hour.

        Start and end times should be returned in local time zone.

        If start time is less than the permit start time, will raise a TemporaryVehicleValidationError.
        """

        now = timezone.localtime()

        start_dt = max(timezone.localtime(isoparse(start_time)), now)

        if start_dt < timezone.localtime(self.start_time):
            raise TemporaryVehicleValidationError(
                _("Temporary vehicle start time has to be after permit start time")
            )

        # prevent end time from being less than start time + 1 hour
        end_dt = max(
            timezone.localtime(isoparse(end_time)),
            start_dt + timezone.timedelta(hours=1),
        )

        # prevent end time from being more than permit end time
        end_dt = min(
            end_dt,
            self.end_time,
        )

        return start_dt, end_dt

    def add_temporary_vehicle(
        self,
        user,
        vehicle,
        start_time: datetime,
        end_time: datetime,
        *,
        check_limit: bool,
    ):
        """Add a new temporary vehicle, creating an event and updating Parkkihubi.

        If `check_limit` is `True` and limit is exceeded, will raise a TemporaryVehicleValidationError.

        """
        if check_limit and self.is_temporary_vehicle_limit_exceeded(user):
            raise TemporaryVehicleValidationError(
                _(
                    "Can not have more than 2 temporary vehicles in 365 days from first one."
                )
            )

        from .temporary_vehicle import TemporaryVehicle

        temp_vehicle = TemporaryVehicle.objects.create(
            vehicle=vehicle,
            end_time=end_time,
            start_time=start_time,
            created_by=user,
            created_at=timezone.now(),
        )

        self.temp_vehicles.add(temp_vehicle)

        ParkingPermitEventFactory.make_add_temporary_vehicle_event(
            self, temp_vehicle, user
        )

        return temp_vehicle

    def remove_temporary_vehicle(self):
        """Remove active temporary vehicle from the permit."""
        active_temp_vehicles = self.temp_vehicles.filter(is_active=True)
        prev_active_temp_vehicles = list(active_temp_vehicles)
        active_temp_vehicles.update(is_active=False)
        for temp_vehicle in prev_active_temp_vehicles:
            ParkingPermitEventFactory.make_remove_temporary_vehicle_event(
                self, temp_vehicle
            )
        return True

    def is_temporary_vehicle_limit_exceeded(self, user) -> bool:
        """Check limit of temporary vehicles.
        A user can only create max 2 temp vehicles over 12 months."""
        return (
            self.temp_vehicles.filter(
                start_time__gte=get_end_time(timezone.now(), -12),
                created_by=user,
            )
            .order_by("-start_time")
            .count()
            >= 2
        )

    def get_unused_order_items(self):
        if self.is_open_ended:
            return self.get_unused_order_items_for_open_ended_permit()
        return self.get_unused_order_items_for_order(self.latest_order)

    def get_unused_order_items_for_open_ended_permit(self):
        order_items = self.latest_order_items.filter(is_refunded=False, permit=self)
        return [
            [
                item,
                item.quantity,
                (
                    timezone.localtime(item.start_time).date(),
                    timezone.localtime(item.end_time).date(),
                ),
            ]
            for item in order_items
        ]

    def get_unused_order_items_for_all_orders(self):
        if self.is_open_ended:
            return self.get_unused_order_items_for_open_ended_permit()
        unused_order_items = []
        for order in self.orders.all().order_by("created_at"):
            unused_order_items.extend(self.get_unused_order_items_for_order(order))
        # sort by order item start time
        unused_order_items.sort(key=lambda x: x[0].start_time)
        return unused_order_items

    def get_unused_order_items_for_order(self, order):
        from .order import OrderStatus

        unused_start_date = timezone.localdate(self.next_period_start_time)

        order_items = order.order_items.filter(
            end_time__date__gte=unused_start_date,
            is_refunded=False,
            order__status=OrderStatus.CONFIRMED,
            permit=self,
        ).order_by("start_time")

        if len(order_items) == 0:
            return []

        # order items may be partially used, so should calculate
        # the remaining quantity and date range starting from
        # unused_start_date
        return [
            *[
                [
                    item,
                    diff_months_ceil(
                        max(
                            unused_start_date,
                            timezone.localtime(item.start_time).date(),
                        ),
                        timezone.localtime(item.end_time).date(),
                    ),
                    (
                        max(
                            unused_start_date,
                            timezone.localtime(item.start_time).date(),
                        ),
                        timezone.localtime(item.end_time).date(),
                    ),
                ]
                for item in order_items
            ],
        ]

    def get_products_for_resident(self):
        if self.next_parking_zone:
            return self.next_parking_zone.products.for_resident()
        return self.parking_zone.products.for_resident()

    def get_products_with_quantities(self):
        """Return a list of product and quantities for the permit"""
        # TODO: currently, company permit type is not available
        qs = self.get_products_for_resident()

        if self.is_open_ended:
            permit_start_date = timezone.localdate(self.start_time)
            product = qs.get_for_date(permit_start_date)
            return [[product, 1, (permit_start_date, None)]]

        if self.is_fixed_period:
            permit_start_date = timezone.localdate(self.start_time)
            permit_end_date = timezone.localdate(self.end_time)
            return qs.get_products_with_quantities(permit_start_date, permit_end_date)

    def get_currently_active_product(self):
        """Use if multiple products for single zone, gets
        the one that's currently active"""

        current_time = timezone.now()
        return self.get_products_for_resident().get_for_date(current_time)


class ParkingPermitEvent(TimestampedModelMixin, UserStampedModelMixin):
    class EventType(models.TextChoices):
        CREATED = "CREATED", _("Created")
        UPDATED = "UPDATED", _("Updated")
        RENEWED = "RENEWED", _("Renewed")
        ENDED = "ENDED", _("Ended")

    class EventKey(models.TextChoices):
        CREATE_PERMIT = "create_permit"
        CREATE_DRAFT_PERMIT = "create_draft_permit"
        UPDATE_DRAFT_PERMIT = "update_draft_permit"
        UPDATE_PERMIT = "update_permit"
        END_PERMIT = "end_permit"

        CREATE_ORDER = "create_order"
        RENEW_ORDER = "renew_order"
        CREATE_REFUND = "create_refund"

        ADD_TEMPORARY_VEHICLE = "add_temporary_vehicle"
        REMOVE_TEMPORARY_VEHICLE = "remove_temporary_vehicle"

        CREATE_CUSTOMER_PERMIT_EXTENSION_REQUEST = (
            "create_customer_permit_extension_request"
        )
        CREATE_ADMIN_PERMIT_EXTENSION_REQUEST = "create_admin_permit_extension_request"

        APPROVE_PERMIT_EXTENSION_REQUEST = "approve_permit_extension_request"
        CANCEL_PERMIT_EXTENSION_REQUEST = "cancel_permit_extension_request"

    type = models.CharField(
        max_length=16, choices=EventType.choices, verbose_name=_("Event type")
    )
    key = models.CharField(max_length=255, choices=EventKey.choices)
    message = models.TextField()
    context = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    validity_period = DateTimeRangeField(null=True)
    parking_permit = models.ForeignKey(
        ParkingPermit, on_delete=models.CASCADE, related_name="events"
    )

    # Generic foreign key; see: https://docs.djangoproject.com/en/3.2/ref/contrib/contenttypes/
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveBigIntegerField(null=True)
    related_object = GenericForeignKey("content_type", "object_id")

    @property
    def translated_message(self):
        return _(self.message) % self.context

    def __str__(self):
        return self.translated_message


class ParkingPermitEventFactory:
    @staticmethod
    def make_admin_create_ext_request_event(ext_request, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=ext_request.permit,
            message=gettext_noop(
                "Permit extension #%(ext_request_id)s created by admin"
            ),
            context={"ext_request_id": ext_request.pk},
            created_by=created_by,
            related_object=ext_request,
            validity_period=ext_request.permit.current_period_range,
            type=ParkingPermitEvent.EventType.UPDATED,
            key=ParkingPermitEvent.EventKey.CREATE_ADMIN_PERMIT_EXTENSION_REQUEST,
        )

    @staticmethod
    def make_customer_create_ext_request_event(ext_request, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=ext_request.permit,
            message=gettext_noop(
                "Permit extension #%(ext_request_id)s created by customer"
            ),
            context={"ext_request_id": ext_request.pk},
            created_by=created_by,
            related_object=ext_request,
            validity_period=ext_request.extension_range,
            type=ParkingPermitEvent.EventType.UPDATED,
            key=ParkingPermitEvent.EventKey.CREATE_CUSTOMER_PERMIT_EXTENSION_REQUEST,
        )

    @staticmethod
    def make_approve_ext_request_event(ext_request, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=ext_request.permit,
            message=gettext_noop("Permit extension #%(ext_request_id)s approved"),
            context={"ext_request_id": ext_request.pk},
            created_by=created_by,
            related_object=ext_request,
            validity_period=ext_request.permit.current_period_range,
            type=ParkingPermitEvent.EventType.UPDATED,
            key=ParkingPermitEvent.EventKey.APPROVE_PERMIT_EXTENSION_REQUEST,
        )

    @staticmethod
    def make_cancel_ext_request_event(ext_request, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=ext_request.permit,
            message=gettext_noop("Permit extension #%(ext_request_id)s cancelled"),
            context={"ext_request_id": ext_request.pk},
            created_by=created_by,
            related_object=ext_request,
            validity_period=ext_request.extension_range,
            type=ParkingPermitEvent.EventType.UPDATED,
            key=ParkingPermitEvent.EventKey.CANCEL_PERMIT_EXTENSION_REQUEST,
        )

    @staticmethod
    def make_create_permit_event(permit: ParkingPermit, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message=gettext_noop("Permit #%(permit_id)s created"),
            context={"permit_id": permit.id},
            validity_period=permit.current_period_range,
            type=ParkingPermitEvent.EventType.CREATED,
            created_by=created_by,
            key=ParkingPermitEvent.EventKey.CREATE_PERMIT,
        )

    @staticmethod
    def make_create_draft_permit_event(permit: ParkingPermit, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message=gettext_noop("Permit #%(permit_id)s draft created"),
            context={"permit_id": permit.id},
            type=ParkingPermitEvent.EventType.CREATED,
            created_by=created_by,
            key=ParkingPermitEvent.EventKey.CREATE_DRAFT_PERMIT,
        )

    @staticmethod
    def make_update_draft_permit_event(permit: ParkingPermit, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message=gettext_noop("Permit #%(permit_id)s draft updated"),
            context={"permit_id": permit.id},
            type=ParkingPermitEvent.EventType.CREATED,
            created_by=created_by,
            key=ParkingPermitEvent.EventKey.UPDATE_DRAFT_PERMIT,
        )

    @staticmethod
    def make_update_permit_event(
        permit: ParkingPermit, created_by=None, changes: dict = None
    ):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message=gettext_noop("Permit #%(permit_id)s updated"),
            context={
                "permit_id": permit.id,
                "changes": flatten_dict(changes or {}),
            },
            validity_period=permit.current_period_range,
            type=ParkingPermitEvent.EventType.UPDATED,
            created_by=created_by,
            key=ParkingPermitEvent.EventKey.UPDATE_PERMIT,
        )

    @staticmethod
    def make_end_permit_event(permit, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message=gettext_noop("Permit #%(permit_id)s ended"),
            context={"permit_id": permit.id},
            type=ParkingPermitEvent.EventType.ENDED,
            created_by=created_by,
            key=ParkingPermitEvent.EventKey.END_PERMIT,
        )

    @staticmethod
    def make_create_order_event(permit: ParkingPermit, order, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message="Order #%(order_id)s created",
            context={"order_id": order.id},
            validity_period=permit.current_period_range,
            type=ParkingPermitEvent.EventType.CREATED,
            created_by=created_by,
            related_object=order,
            key=ParkingPermitEvent.EventKey.CREATE_ORDER,
        )

    @staticmethod
    def make_create_ext_request_order_event(
        permit: ParkingPermit, order, start_time, end_time, created_by=None
    ):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message="Order #%(order_id)s created",
            context={"order_id": order.id},
            validity_period=(start_time, end_time),
            type=ParkingPermitEvent.EventType.CREATED,
            created_by=created_by,
            related_object=order,
            key=ParkingPermitEvent.EventKey.CREATE_ORDER,
        )

    @staticmethod
    def make_renew_order_event(permit: ParkingPermit, order, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message="Order #%(order_id)s renewed",
            context={"order_id": order.id},
            validity_period=permit.current_period_range,
            type=ParkingPermitEvent.EventType.RENEWED,
            created_by=created_by,
            related_object=order,
            key=ParkingPermitEvent.EventKey.RENEW_ORDER,
        )

    @staticmethod
    def make_create_refund_event(permit, refund, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message=gettext_noop("Refund #%(refund_id)s created"),
            context={"refund_id": refund.id},
            validity_period=permit.current_period_range,
            type=ParkingPermitEvent.EventType.CREATED,
            created_by=created_by,
            related_object=refund,
            key=ParkingPermitEvent.EventKey.CREATE_REFUND,
        )

    @staticmethod
    def make_add_temporary_vehicle_event(permit, temp_vehicle, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message=gettext_noop(
                "Temporary vehicle #%(temp_vehicle_reg_number)s added to permit"
            ),
            context={
                "temp_vehicle_reg_number": temp_vehicle.vehicle.registration_number
            },
            validity_period=temp_vehicle.period_range,
            type=ParkingPermitEvent.EventType.UPDATED,
            created_by=created_by,
            related_object=temp_vehicle,
            key=ParkingPermitEvent.EventKey.ADD_TEMPORARY_VEHICLE,
        )

    @staticmethod
    def make_remove_temporary_vehicle_event(permit, temp_vehicle, created_by=None):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message=gettext_noop(
                "Temporary vehicle #%(temp_vehicle_reg_number)s removed from permit"
            ),
            context={
                "temp_vehicle_reg_number": temp_vehicle.vehicle.registration_number
            },
            validity_period=temp_vehicle.period_range,
            type=ParkingPermitEvent.EventType.UPDATED,
            created_by=created_by,
            related_object=temp_vehicle,
            key=ParkingPermitEvent.EventKey.REMOVE_TEMPORARY_VEHICLE,
        )
