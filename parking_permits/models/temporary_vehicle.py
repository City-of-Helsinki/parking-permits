from django.conf import settings
from django.contrib.gis.db import models
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _

from .mixins import TimestampedModelMixin
from .vehicle import Vehicle


class TemporaryVehicle(TimestampedModelMixin):
    vehicle = models.ForeignKey(
        Vehicle,
        verbose_name=_("Vehicle"),
        on_delete=models.PROTECT,
    )
    start_time = models.DateTimeField(_("Start time"), default=tz.now)
    end_time = models.DateTimeField(_("End time"))
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Created by"),
        related_name="+",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Temporary vehicle")
        verbose_name_plural = _("Temporary vehicles")

    def __str__(self):
        return str(self.vehicle)

    @property
    def period_range(self):
        return self.start_time, self.end_time
