from decimal import Decimal

from django.conf import settings
from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from parking_permits.utils import calc_vat_price

from .mixins import TimestampedModelMixin, UserStampedModelMixin

VAT_PERCENT = Decimal(0.24)


class RefundStatus(models.TextChoices):
    OPEN = "OPEN", _("Open")
    REQUEST_FOR_APPROVAL = "REQUEST_FOR_APPROVAL", _("Request for approval")
    ACCEPTED = "ACCEPTED", _("Accepted")
    REJECTED = "REJECTED", _("Rejected")


class Refund(TimestampedModelMixin, UserStampedModelMixin):
    name = models.CharField(_("Name"), max_length=200, blank=True)
    order = models.ForeignKey(
        "Order",
        verbose_name=_("Order"),
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    permits = models.ManyToManyField(
        "ParkingPermit",
        verbose_name=_("Permits"),
        related_name="refunds",
        blank=True,
    )
    amount = models.DecimalField(
        _("Amount"), default=0.00, max_digits=6, decimal_places=2
    )
    iban = models.CharField(max_length=30, blank=True)
    status = models.CharField(
        _("Status"),
        max_length=32,
        choices=RefundStatus.choices,
        default=RefundStatus.OPEN,
    )
    description = models.TextField(_("Description"), blank=True)
    accepted_at = models.DateTimeField(_("Accepted at"), null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Accepted by"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    # this is hard coded at the moment. At some point should be
    # a field we can calculate when the refund is generated.
    vat_percent = VAT_PERCENT

    class Meta:
        verbose_name = _("Refund")
        verbose_name_plural = _("Refunds")

    def __str__(self):
        return f"{self.name} ({self.iban})"

    @property
    def vat(self):
        """Calculate the VAT amount.
        The VAT amount is hard coded here because we do not know the % of individual
        unused items in this model. In future this should probably be stored as a separate field.
        """
        return calc_vat_price(self.amount, self.vat_percent)
