from datetime import datetime

from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from .. import constants
from .customer import Customer
from .mixins import TimestampedModelMixin, UUIDPrimaryKeyMixin
from .parking_zone import ParkingZone
from .vehicle import Vehicle


def get_next_identifier():
    last = ParkingPermit.objects.order_by("-identifier").first()
    if not last:
        return 80000000
    return last.identifier + 1


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
    start_time = models.DateTimeField(_("Start time"), default=datetime.now)
    end_time = models.DateTimeField(_("End time"), blank=True, null=True)
    primary_vehicle = models.BooleanField(null=False, default=True)
    contract_type = models.CharField(
        _("Contract type"),
        max_length=16,
        default=constants.ContractType.OPEN_ENDED.value,
        choices=[(tag.value, tag.value) for tag in constants.ContractType],
    )
    month_count = models.IntegerField(_("Month count"), default=0)

    class Meta:
        db_table = "parking_permit"
        verbose_name = _("Parking permit")
        verbose_name_plural = _("Parking permits")

    def __str__(self):
        return "%s" % self.identifier
