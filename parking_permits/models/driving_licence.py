from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from .driving_class import DrivingClass
from .mixins import TimestampedModelMixin


class DrivingLicence(TimestampedModelMixin):
    customer = models.OneToOneField(
        "Customer",
        verbose_name=_("Customer"),
        on_delete=models.PROTECT,
        related_name="driving_licence",
    )
    driving_classes = models.ManyToManyField(DrivingClass)
    start_date = models.DateField(_("Start date"))
    end_date = models.DateField(_("End date"), null=True, blank=True)
    active = models.BooleanField(null=False, default=True)

    class Meta:
        verbose_name = _("Driving licence")
        verbose_name_plural = _("Driving licences")

    def __str__(self):
        return f"{self.customer}, active: {self.active}"
