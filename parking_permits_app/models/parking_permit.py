import decimal

import reversion
from django.contrib.gis.db import models
from django.utils import timezone
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _

from .. import constants
from ..constants import (
    LOW_EMISSION_DISCOUNT,
    SECONDARY_VEHICLE_PRICE_INCREASE,
    ContractType,
)
from ..utils import calc_months_diff
from .customer import Customer
from .mixins import TimestampedModelMixin, UUIDPrimaryKeyMixin
from .parking_zone import ParkingZone
from .vehicle import Vehicle


def get_next_identifier():
    last = ParkingPermit.objects.order_by("-identifier").first()
    if not last:
        return 80000000
    return last.identifier + 1


@reversion.register()
class ParkingPermit(TimestampedModelMixin, UUIDPrimaryKeyMixin):
    customer = models.ForeignKey(
        Customer,
        verbose_name=_("Customer"),
        on_delete=models.PROTECT,
        blank=False,
        null=False,
    )
    vehicle = models.ForeignKey(
        Vehicle,
        verbose_name=_("Vehicle"),
        on_delete=models.PROTECT,
        blank=False,
        null=False,
    )
    parking_zone = models.ForeignKey(
        ParkingZone,
        verbose_name=_("Parking zone"),
        on_delete=models.PROTECT,
        blank=False,
        null=False,
    )
    status = models.CharField(
        _("Status"),
        max_length=32,
        default=constants.ParkingPermitStatus.DRAFT.value,
        choices=[(tag.value, tag.value) for tag in constants.ParkingPermitStatus],
    )
    identifier = models.IntegerField(
        default=get_next_identifier, editable=False, unique=True, db_index=True
    )
    consent_low_emission_accepted = models.BooleanField(null=False, default=False)
    start_time = models.DateTimeField(_("Start time"), default=tz.now)
    end_time = models.DateTimeField(_("End time"), blank=True, null=True)
    primary_vehicle = models.BooleanField(null=False, default=True)
    contract_type = models.CharField(
        _("Contract type"),
        max_length=16,
        default=constants.ContractType.OPEN_ENDED.value,
        choices=[(tag.value, tag.value) for tag in constants.ContractType],
    )
    start_type = models.CharField(
        _("Start type"),
        max_length=16,
        default=constants.StartType.IMMEDIATELY.value,
        choices=[(tag.value, tag.value) for tag in constants.StartType],
    )
    month_count = models.IntegerField(_("Month count"), default=1)

    order_id = models.CharField(max_length=50, blank=True, null=True)
    subscription_id = models.CharField(
        max_length=50, unique=True, blank=True, null=True
    )

    class Meta:
        db_table = "parking_permit"
        verbose_name = _("Parking permit")
        verbose_name_plural = _("Parking permits")

    def __str__(self):
        return "%s" % self.identifier

    @property
    def months_left(self):
        if self.contract_type == ContractType.OPEN_ENDED or not self.end_time:
            return None
        today = timezone.now().today()
        return calc_months_diff(today, self.end_time.date())

    def get_prices(self):
        monthly_price = self.parking_zone.price
        month_count = self.month_count

        if self.contract_type == constants.ContractType.OPEN_ENDED.value:
            month_count = 1
        if not self.primary_vehicle:
            increase = decimal.Decimal(SECONDARY_VEHICLE_PRICE_INCREASE) / 100
            monthly_price += increase * monthly_price

        if self.vehicle.is_low_emission:
            discount = decimal.Decimal(LOW_EMISSION_DISCOUNT) / 100
            monthly_price -= discount * monthly_price

        return monthly_price * month_count, monthly_price
