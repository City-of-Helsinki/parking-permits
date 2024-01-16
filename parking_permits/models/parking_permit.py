import json
import logging
from decimal import Decimal

import requests
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

from ..constants import ParkingPermitEndType
from ..exceptions import ParkkihubiPermitError, PermitCanNotBeEnded
from ..utils import (
    calc_vat_price,
    diff_months_ceil,
    end_date_to_datetime,
    flatten_dict,
    get_end_time,
    get_permit_prices,
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


class ParkingPermitStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    ARRIVED = "ARRIVED", _("Arrived")
    PROCESSING = "PROCESSING", _("Processing")
    ACCEPTED = "ACCEPTED", _("Accepted")
    REJECTED = "REJECTED", _("Rejected")
    PAYMENT_IN_PROGRESS = "PAYMENT_IN_PROGRESS", _("Payment in progress")
    VALID = "VALID", _("Valid")
    CLOSED = "CLOSED", _("Closed")


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
    vehicle_changed = models.BooleanField(default=False)
    synced_with_parkkihubi = models.BooleanField(default=False)
    vehicle_changed_date = models.DateField(
        _("Vehicle changed date"), null=True, blank=True
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
        return self.temporary_vehicles.filter(is_active=True).first()

    @property
    def consent_low_emission_accepted(self):
        return self.vehicle.consent_low_emission_accepted

    @property
    def latest_order(self):
        """Get the latest order for the permit

        Multiple orders can be created for the same permit
        when, for example, the vehicle or the address of
        the permit is changed.
        """
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
    def checkout_url(self):
        if self.latest_order and self.latest_order.talpa_checkout_url:
            return self.latest_order.talpa_checkout_url
        return None

    @property
    def latest_order_items(self):
        """Get latest order items for the permit"""
        return self.order_items.filter(order=self.latest_order)

    @property
    def latest_order_item(self):
        return self.latest_order_items.first() or None

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
        return self.is_valid and (
            self.end_time is None or self.current_period_end_time < self.end_time
        )

    @property
    def months_used(self):
        now = timezone.now()
        diff_months = diff_months_ceil(self.start_time, now)
        if self.is_fixed_period:
            return min(self.month_count, diff_months)
        return diff_months

    @property
    def months_left(self):
        if self.is_open_ended:
            return None
        return self.month_count - self.months_used

    @property
    def current_period_start_time(self):
        if self.is_open_ended:
            return self.start_time
        return self.start_time + relativedelta(months=self.months_used - 1)

    @property
    def current_period_end_time(self):
        return self.current_period_end_time_with_fixed_months(self.months_used)

    @property
    def current_period_range(self):
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
        return self.get_refund_amount_for_unused_items()

    @property
    def zone_changed(self):
        addresses = [self.customer.primary_address, self.customer.other_address]
        return not any(
            address and address.zone == self.parking_zone for address in addresses
        )

    def current_period_end_time_with_fixed_months(self, months):
        end_time = get_end_time(self.start_time, months)
        return max(self.start_time, end_time)

    def get_price_change_list(self, new_zone, is_low_emission):
        """Get a list of price changes if the permit is changed

        Only vehicle and zone change will affect the price

        Args:
            new_zone: new zone used in the permit
            is_low_emission: True if the new vehicle is a low emission one

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
                    # if the product is different or diff price is different,
                    # create a new price change item
                    price_change_vat = calc_vat_price(
                        diff_price, new_product.vat
                    ).quantize(Decimal("0.0001"))

                    price_change_list.append(
                        {
                            "product": new_product.name,
                            "previous_price": previous_price,
                            "new_price": new_price,
                            "price_change_vat": price_change_vat,
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
        self.save()

    def get_refund_amount_for_unused_items(self):
        total = Decimal(0)
        if not self.can_be_refunded:
            return total

        unused_order_items = self.get_unused_order_items()

        for order_item, quantity, date_range in unused_order_items:
            total += order_item.unit_price * quantity
        return total

    def get_unused_order_items(self):
        unused_start_date = timezone.localdate(self.next_period_start_time)
        if not self.is_fixed_period:
            order_items = self.latest_order_items
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

        order_items = self.latest_order_items.filter(
            end_time__date__gte=unused_start_date
        ).order_by("start_time")

        if len(order_items) == 0:
            return []

        # first order item is partially used, so should calculate
        # the remaining quantity and date range starting from
        # unused_start_date
        first_item = order_items[0]
        first_item_unused_quantity = diff_months_ceil(
            unused_start_date, timezone.localtime(first_item.end_time).date()
        )
        first_item_with_quantity = [
            first_item,
            first_item_unused_quantity,
            (unused_start_date, timezone.localtime(first_item.end_time).date()),
        ]

        return [
            first_item_with_quantity,
            *[
                [
                    item,
                    item.quantity,
                    (
                        timezone.localtime(item.start_time).date(),
                        timezone.localtime(item.end_time).date(),
                    ),
                ]
                for item in order_items[1:]
            ],
        ]

    def get_products_with_quantities(self):
        """Return a list of product and quantities for the permit"""
        # TODO: currently, company permit type is not available
        if self.next_parking_zone:
            qs = self.next_parking_zone.products.for_resident()
        else:
            qs = self.parking_zone.products.for_resident()

        if self.is_open_ended:
            permit_start_date = timezone.localdate(self.start_time)
            product = qs.get_for_date(permit_start_date)
            return [[product, 1, (permit_start_date, None)]]

        if self.is_fixed_period:
            permit_start_date = timezone.localdate(self.start_time)
            permit_end_date = timezone.localdate(self.end_time)
            return qs.get_products_with_quantities(permit_start_date, permit_end_date)

    def update_parkkihubi_permit(self):
        if settings.DEBUG_SKIP_PARKKIHUBI_SYNC:  # pragma: no cover
            logger.debug("Skipped Parkkihubi sync in permit update.")
            return

        response = requests.patch(
            f"{settings.PARKKIHUBI_OPERATOR_ENDPOINT}{str(self.id)}/",
            data=json.dumps(self._get_parkkihubi_data(), default=str),
            headers=self._get_parkkihubi_headers(),
        )
        self.synced_with_parkkihubi = response.status_code == 200
        self.save()

        if response.status_code == 200:
            logger.info("Parkkihubi update permit")
        else:
            logger.error(
                "Failed to update permit to Parkkihubi."
                f"Error: {response.status_code} {response.reason}. "
                f"Detail: {response.text}"
            )
            raise ParkkihubiPermitError(
                "Cannot update permit to Parkkihubi."
                f"Error: {response.status_code} {response.reason}."
            )

    def create_parkkihubi_permit(self):
        if settings.DEBUG_SKIP_PARKKIHUBI_SYNC:  # pragma: no cover
            logger.debug("Skipped Parkkihubi sync in permit creation.")
            return

        response = requests.post(
            settings.PARKKIHUBI_OPERATOR_ENDPOINT,
            data=json.dumps(self._get_parkkihubi_data(), default=str),
            headers=self._get_parkkihubi_headers(),
        )
        self.synced_with_parkkihubi = response.status_code == 201
        self.save()

        if response.status_code == 201:
            logger.info("Parkkihubi permit created")
        else:
            logger.error(
                "Failed to create permit to Parkkihubi."
                f"Error: {response.status_code} {response.reason}. "
                f"Detail: {response.text}"
            )
            raise ParkkihubiPermitError(
                "Cannot create permit to Parkkihubi."
                f"Error: {response.status_code} {response.reason}."
            )

    def _get_parkkihubi_headers(self):
        return {
            "Authorization": f"ApiKey {settings.PARKKIHUBI_TOKEN}",
            "Content-Type": "application/json",
        }

    def _get_parkkihubi_data(self):
        subjects = []
        start_time = str(self.start_time)
        end_time = (
            str(get_end_time(self.start_time, 30))
            if not self.end_time
            else str(self.end_time)
        )
        registration_number = self.vehicle.registration_number

        active_temporary_vehicle = self.active_temporary_vehicle
        if active_temporary_vehicle:
            subjects.append(
                {
                    "start_time": str(start_time),
                    "end_time": str(self.active_temporary_vehicle.start_time),
                    "registration_number": registration_number,
                }
            )
            subjects.append(
                {
                    "start_time": str(self.active_temporary_vehicle.start_time),
                    "end_time": str(self.active_temporary_vehicle.end_time),
                    "registration_number": self.active_temporary_vehicle.vehicle.registration_number,
                }
            )
            subjects.append(
                {
                    "start_time": str(self.active_temporary_vehicle.end_time),
                    "end_time": str(end_time),
                    "registration_number": registration_number,
                }
            )
        else:
            subjects.append(
                {
                    "start_time": str(start_time),
                    "end_time": str(end_time),
                    "registration_number": registration_number,
                }
            )

        return {
            "series": settings.PARKKIHUBI_PERMIT_SERIES,
            "domain": settings.PARKKIHUBI_DOMAIN,
            "external_id": str(self.id),
            "properties": {"permit_type": self.type},
            "subjects": subjects,
            "areas": [
                {
                    "start_time": start_time,
                    "end_time": end_time,
                    "area": self.parking_zone.name,
                }
            ],
        }


class ParkingPermitEvent(TimestampedModelMixin, UserStampedModelMixin):
    class EventType(models.TextChoices):
        CREATED = "CREATED", _("Created")
        UPDATED = "UPDATED", _("Updated")
        RENEWED = "RENEWED", _("Renewed")
        ENDED = "ENDED", _("Ended")

    class EventKey(models.TextChoices):
        CREATE_PERMIT = "create_permit"
        UPDATE_PERMIT = "update_permit"
        END_PERMIT = "end_permit"
        CREATE_ORDER = "create_order"
        RENEW_ORDER = "renew_order"
        CREATE_REFUND = "create_refund"
        ADD_TEMPORARY_VEHICLE = "add_temporary_vehicle"
        REMOVE_TEMPORARY_VEHICLE = "remove_temporary_vehicle"

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
    def make_update_permit_event(
        permit: ParkingPermit, created_by=None, changes: dict = None
    ):
        return ParkingPermitEvent.objects.create(
            parking_permit=permit,
            message=gettext_noop("Permit #%(permit_id)s updated"),
            context={
                "permit_id": permit.id,
                "changes": flatten_dict(changes or dict()),
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
            validity_period=permit.current_period_range,
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
            validity_period=permit.current_period_range,
            type=ParkingPermitEvent.EventType.UPDATED,
            created_by=created_by,
            related_object=temp_vehicle,
            key=ParkingPermitEvent.EventKey.REMOVE_TEMPORARY_VEHICLE,
        )
