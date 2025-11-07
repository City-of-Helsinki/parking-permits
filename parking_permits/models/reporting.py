from django.db import models
from django.utils.translation import gettext_lazy as _

from parking_permits.models.parking_permit import ContractType


class PermitCountSnapshot(models.Model):
    """Represents a daily snapshot of the counts of valid parking
    permits on the given date grouped by relevant dimensions."""

    permit_count = models.IntegerField(_("Permit count"))

    date = models.DateField(_("Date"))

    parking_zone_name = models.CharField(_("Parking zone name"), max_length=128)
    parking_zone_description = models.TextField(_("Parking zone description"))
    parking_zone_description_sv = models.TextField(_("Parking zone description sv"))

    low_emission = models.BooleanField(_("Low-emission"))

    primary_vehicle = models.BooleanField(_("Primary vehicle"))

    contract_type = models.CharField(
        _("Contract type"),
        max_length=16,
        choices=ContractType.choices,
    )

    class Meta:
        verbose_name = _("Permit count snapshot")
        verbose_name_plural = _("Permit count snapshots")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "date",
                    "parking_zone_name",
                    "parking_zone_description",
                    "parking_zone_description_sv",
                    "low_emission",
                    "primary_vehicle",
                    "contract_type",
                ),
                name="unique_daily_snapshot",
            )
        ]
