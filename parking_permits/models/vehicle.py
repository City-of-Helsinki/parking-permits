from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _

from .mixins import TimestampedModelMixin


class VehicleClass(models.TextChoices):
    M1 = "M1", _("M1")
    M1G = "M1G", _("M1G")
    M2 = "M2", _("M2")
    M2G = "M2G", _("M2G")
    N1 = "N1", _("N1")
    N1G = "N1G", _("N1G")
    N2 = "N2", _("N2")
    N2G = "N2G", _("N2G")
    L3eA1 = "L3e-A1", _("L3e-A1")
    L3eA2 = "L3e-A2", _("L3e-A2")
    L3eA3 = "L3e-A3", _("L3e-A3")
    L4e = "L4e", _("L4e")
    L5eA = "L5e-A", _("L5e-A")
    L5eB = "L5e-B", _("L5e-B")
    L6eA = "L6e-A", _("L6e-A")
    L6eB = "L6e-B", _("L6e-B")
    L6eBP = "L6e-BP", _("L6e-BP")
    L6eBU = "L6e-BU", _("L6e-BU")


def is_low_emission_vehicle(power_type):
    return power_type.is_electric


class VehiclePowerType(models.Model):
    name = models.CharField(_("Name"), max_length=100, blank=True)
    identifier = models.CharField(_("Identifier"), max_length=10)

    class Meta:
        verbose_name = _("Vehicle power type")
        verbose_name_plural = _("Vehicle power types")

    def __str__(self):
        return f"Identifier: {self.identifier}, Name: {self.name}"

    @property
    def is_electric(self):
        return self.identifier == "04"


class VehicleUser(models.Model):
    national_id_number = models.CharField(
        _("National identification number"),
        max_length=50,
        null=True,
        blank=True,
        unique=True,
    )

    class Meta:
        verbose_name = _("Vehicle user")
        verbose_name_plural = _("Vehicle users")

    def __str__(self):
        return self.national_id_number


class Vehicle(TimestampedModelMixin):
    power_type = models.ForeignKey(
        VehiclePowerType,
        verbose_name=_("power_type"),
        related_name="vehicles",
        on_delete=models.PROTECT,
    )
    vehicle_class = models.CharField(
        _("VehicleClass"), max_length=16, choices=VehicleClass.choices, blank=True
    )
    manufacturer = models.CharField(_("Manufacturer"), max_length=100)
    model = models.CharField(_("Model"), max_length=100)

    registration_number = models.CharField(
        _("Registration number"), max_length=24, unique=True
    )
    weight = models.IntegerField(_("Total weigh of vehicle"), default=0)
    consent_low_emission_accepted = models.BooleanField(default=False)
    serial_number = models.CharField(_("Serial number"), max_length=100, blank=True)
    last_inspection_date = models.DateField(
        _("Last inspection date"), null=True, blank=True
    )
    updated_from_traficom_on = models.DateTimeField(
        _("Update from traficom on"), null=True, blank=True
    )
    users = models.ManyToManyField(
        VehicleUser, verbose_name=_("Vehicle users"), related_name="vehicles"
    )

    restrictions = ArrayField(
        verbose_name=_("Traficom Restrictions"),
        base_field=models.CharField(max_length=2, blank=True),
        default=list,
    )

    class Meta:
        verbose_name = _("Vehicle")
        verbose_name_plural = _("Vehicles")

    @property
    def is_low_emission(self):
        return is_low_emission_vehicle(self.power_type)

    @property
    def description(self):
        return f"{_('Vehicle')}: {str(self)}"

    def __str__(self):
        vehicle_str = f"{self.registration_number}" or ""
        if self.manufacturer:
            vehicle_str += f" ({self.manufacturer}"
            if self.model:
                vehicle_str += f", {self.model}"
            vehicle_str += ")"
        return vehicle_str
