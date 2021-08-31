from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.gis.geos import GEOSGeometry
from django.utils.translation import gettext_lazy as _

from ..services.kmo import get_wfs_result
from .mixins import TimestampedModelMixin
from .parking_zone import ParkingZone


class Address(TimestampedModelMixin):
    id = models.TextField(primary_key=True, unique=True, editable=False)
    street_name = models.CharField(
        _("Street name"), max_length=128, blank=False, null=False
    )
    street_name_sv = models.CharField(
        _("Street name sv"), max_length=128, blank=False, null=False, default=""
    )
    street_number = models.CharField(
        _("Street number"), max_length=128, blank=False, null=False
    )
    city = models.CharField(_("City"), max_length=128, blank=False, null=False)
    postal_code = models.CharField(
        _("Postal code"), max_length=5, blank=True, null=True, default=None
    )
    location = models.PointField(
        _("Location (2D)"), srid=settings.SRID, blank=True, null=True
    )
    zone = models.ForeignKey(
        ParkingZone,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Zone"),
    )

    class Meta:
        db_table = "address"
        verbose_name = _("Address")
        verbose_name_plural = _("Addresses")

    def __str__(self):
        return "%s %s, %s" % (
            self.street_name,
            self.street_number,
            self.city,
        )

    def convert_to_geosgeometry(self, geometry):
        return GEOSGeometry(str(geometry))

    def get_kmo_features(self):
        if not self.location:
            results = get_wfs_result(self.street_name, self.street_number)
            address_feature = next(
                feature
                for feature in results.get("features")
                if feature.get("geometry").get("type") == "Point"
            )
            address_property = address_feature.get("properties")
            location = self.convert_to_geosgeometry(address_feature.get("geometry"))
            zone = ParkingZone.objects.filter(location__intersects=location).first()
            return address_property.get("gatan"), location, zone
        return self.street_name_sv, self.location, self.zone

    def save(self, update_fields=None, *args, **kwargs):
        if (
            update_fields is None
            or "street_name" in update_fields
            or "street_number" in update_fields
        ):
            street_name_sv, location, zone = self.get_kmo_features()
            self.street_name_sv = street_name_sv
            self.location = location
            self.zone = zone

        super().save(update_fields=update_fields, *args, **kwargs)
