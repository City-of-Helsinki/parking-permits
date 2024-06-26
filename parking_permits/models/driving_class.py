from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from .mixins import TimestampedModelMixin
from .vehicle import VehicleClass

ALLOWED_VEHICLE_CLASSES = {
    "AM/121": (VehicleClass.L6eB,),
    "A1": (VehicleClass.L3eA1,),
    "A2": (
        VehicleClass.L3eA1,
        VehicleClass.L3eA2,
    ),
    "A": (
        VehicleClass.L3eA1,
        VehicleClass.L3eA2,
        VehicleClass.L3eA3,
    ),
    "B": (
        VehicleClass.M1,
        VehicleClass.M1G,
        VehicleClass.N1,
        VehicleClass.N1G,
        VehicleClass.L6eB,
    ),
    "BE": (
        VehicleClass.M1,
        VehicleClass.M1G,
        VehicleClass.N1,
        VehicleClass.N1G,
        VehicleClass.L6eB,
    ),
    "B/96": (
        VehicleClass.M1,
        VehicleClass.M1G,
        VehicleClass.N1,
        VehicleClass.N1G,
        VehicleClass.L6eB,
    ),
    "C": (
        VehicleClass.N2,
        VehicleClass.N2G,
    ),
    "C1": (
        VehicleClass.N2,
        VehicleClass.N2G,
    ),
    "C1E": (
        VehicleClass.N2,
        VehicleClass.N2G,
    ),
    "CE": (
        VehicleClass.N2,
        VehicleClass.N2G,
    ),
    "D": (
        VehicleClass.M2,
        VehicleClass.M2G,
    ),
    "D1": (
        VehicleClass.M2,
        VehicleClass.M2G,
    ),
    "DE": (
        VehicleClass.M2,
        VehicleClass.M2G,
    ),
    "D1E": (
        VehicleClass.M2,
        VehicleClass.M2G,
    ),
}


class DrivingClass(TimestampedModelMixin):
    identifier = models.CharField(_("Identifier"), max_length=32)

    class Meta:
        verbose_name = _("Driving class")
        verbose_name_plural = _("Driving classes")

    def __str__(self):
        return self.identifier

    @property
    def vehicle_classes(self):
        return ALLOWED_VEHICLE_CLASSES.get(self.identifier, ())
