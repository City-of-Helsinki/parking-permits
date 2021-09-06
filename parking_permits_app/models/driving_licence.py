import arrow
from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from .customer import Customer
from .driving_class import DrivingClass
from .mixins import TimestampedModelMixin, UUIDPrimaryKeyMixin


class DrivingLicence(TimestampedModelMixin, UUIDPrimaryKeyMixin):
    customer = models.OneToOneField(
        Customer,
        verbose_name=_("Customer"),
        on_delete=models.PROTECT,
        related_name="driving_licence",
    )
    driving_classes = models.ManyToManyField(DrivingClass)
    valid_start = models.DateTimeField(_("Valid start"))
    valid_end = models.DateTimeField(_("Valid end"))
    active = models.BooleanField(null=False, default=True)

    def is_valid_for_vehicle(self, vehicle):
        is_not_expired = self.valid_end > arrow.utcnow()
        is_not_suspended = self.active

        return is_not_expired and is_not_suspended

    class Meta:
        db_table = "driving_licence"
        verbose_name = _("Driving licence")
        verbose_name_plural = _("Driving licences")

    def __str__(self):
        return "%s, active: %s" % (self.customer, self.active)
