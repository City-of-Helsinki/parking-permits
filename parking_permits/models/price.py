from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from .mixins import TimestampedModelMixin


class PriceType(models.TextChoices):
    COMPANY = "COMPANY", _("Company")
    RESIDENT = "RESIDENT", _("Resident")


class Price(TimestampedModelMixin):
    zone = models.ForeignKey(
        "ParkingZone",
        verbose_name=_("Zone"),
        on_delete=models.PROTECT,
        related_name="prices",
    )
    price = models.DecimalField(_("Price"), max_digits=6, decimal_places=2)
    type = models.CharField(
        _("Type"), max_length=20, choices=PriceType.choices, default=PriceType.RESIDENT
    )
    year = models.IntegerField(_("Year"))

    class Meta:
        verbose_name = _("Price")
        verbose_name_plural = _("Prices")
        unique_together = ["zone", "type", "year"]

    def __str__(self):
        return f"{self.price}€ ({self.year})"
