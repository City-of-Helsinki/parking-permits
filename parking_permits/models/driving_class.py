from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from .mixins import TimestampedModelMixin
from .vehicle import VehicleClass

ALLOWED_VEHICLE_CLASSES = {
    "AM/121": (VehicleClass.L6eB,),
    "A1": (VehicleClass.L3eA1,),
    "A2": (VehicleClass.L3eA2,),
    "A": (
        VehicleClass.L3eA1,
        VehicleClass.L3eA2,
        VehicleClass.L3eA3,
    ),
    "B": (
        VehicleClass.M1,
        VehicleClass.M2,  # M2 mass less than 3500KG
        VehicleClass.N1,
        VehicleClass.L6eB,
    ),
    "C": (VehicleClass.N2,),
    "D": (VehicleClass.M2,),  # M2 mass not more than 3500 - 4000KG
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
