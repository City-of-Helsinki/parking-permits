from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from .mixins import TimestampedModelMixin, UserStampedModelMixin
from .parking_zone import ParkingZone


class Announcement(UserStampedModelMixin, TimestampedModelMixin):
    subject_en = models.CharField(_("Subject (EN)"), max_length=255)
    content_en = models.TextField(_("Content (EN)"))
    subject_fi = models.CharField(_("Subject (FI)"), max_length=255)
    content_fi = models.TextField(_("Content (FI)"))
    subject_sv = models.CharField(_("Subject (SV)"), max_length=255)
    content_sv = models.TextField(_("Content (SV)"))
    _parking_zones = models.ManyToManyField(ParkingZone, "announcements")
    emails_handled = models.BooleanField(_("Emails handled"), default=False)

    @property
    def parking_zones(self):
        return self._parking_zones.all()
