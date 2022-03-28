from datetime import datetime

import arrow
from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from .mixins import TimestampedModelMixin, UUIDPrimaryKeyMixin


class VehiclePowerType(models.TextChoices):
    ELECTRIC = "ELECTRIC", _("Electric")
    BENSIN = "BENSIN", _("Bensin")
    DIESEL = "DIESEL", _("Diesel")
    BIFUEL = "BIFUEL", _("Bifuel")


class VehicleClass(models.TextChoices):
    M1 = "M1", _("M1")
    M2 = "M2", _("M2")
    N1 = "N1", _("N1")
    N2 = "N2", _("N2")
    L3eA1 = "L3e-A1", _("L3e-A1")
    L3eA2 = "L3e-A2", _("L3e-A2")
    L3eA3 = "L3e-A3", _("L3e-A3")
    L3eA1E = "L3e-A1E", _("L3e-A1E")
    L3eA2E = "L3e-A2E", _("L3e-A2E")
    L3eA3E = "L3e-A3E", _("L3e-A3E")
    L3eA1T = "L3e-A1T", _("L3e-A1T")
    L3eA2T = "L3e-A2T", _("L3e-A2T")
    L3eA3T = "L3e-A3T", _("L3e-A3T")
    L4e = "L4e", _("L4e")
    L5eA = "L5e-A", _("L5e-A")
    L5eB = "L5e-B", _("L5e-B")
    L6eA = "L6e-A", _("L6e-A")
    L6eB = "L6e-B", _("L6e-B")
    L6eBP = "L6e-BP", _("L6e-BP")
    L6eBU = "L6e-BU", _("L6e-BU")


class EmissionType(models.TextChoices):
    NEDC = "NEDC", _("NEDC")
    WLTP = "WLTP", _("WLTP")


class LowEmissionCriteria(TimestampedModelMixin, UUIDPrimaryKeyMixin):
    power_type = models.CharField(
        _("Power type"), max_length=50, choices=VehiclePowerType.choices
    )
    nedc_max_emission_limit = models.IntegerField(
        _("NEDC maximum emission limit"), blank=True, null=True
    )
    wltp_max_emission_limit = models.IntegerField(
        _("WLTP maximum emission limit"), blank=True, null=True
    )
    euro_min_class_limit = models.IntegerField(
        _("Euro minimum class limit"), blank=True, null=True
    )
    start_date = models.DateField(_("Start date"))
    end_date = models.DateField(_("End date"), blank=True, null=True)

    class Meta:
        verbose_name = _("Low-emission criteria")
        verbose_name_plural = _("Low-emission criterias")

    def __str__(self):
        return "%s, NEDC: %s, WLTP: %s, EURO: %s" % (
            self.power_type,
            self.nedc_max_emission_limit,
            self.wltp_max_emission_limit,
            self.euro_min_class_limit,
        )


class Vehicle(TimestampedModelMixin, UUIDPrimaryKeyMixin):
    power_type = models.CharField(
        _("Power type"), max_length=50, choices=VehiclePowerType.choices, blank=True
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
    euro_class = models.IntegerField(_("Euro class"), blank=True, null=True)
    emission = models.IntegerField(_("Emission"), blank=True, null=True)
    consent_low_emission_accepted = models.BooleanField(default=False)
    emission_type = models.CharField(
        _("Emission type"),
        max_length=16,
        choices=EmissionType.choices,
        default=EmissionType.WLTP,
    )
    serial_number = models.CharField(_("Serial number"), max_length=100, blank=True)
    last_inspection_date = models.DateField(
        _("Last inspection date"), null=True, blank=True
    )

    def is_due_for_inspection(self):
        return (
            self.last_inspection_date is not None
            and arrow.utcnow().date() > self.last_inspection_date
        )

    @property
    def is_low_emission(self):
        if self.power_type == VehiclePowerType.ELECTRIC:
            return True
        try:
            le_criteria = LowEmissionCriteria.objects.get(
                power_type=self.power_type,
                start_date__lte=datetime.today(),
                end_date__gte=datetime.today(),
            )
        except LowEmissionCriteria.DoesNotExist:
            return False

        if not self.euro_class or self.euro_class < le_criteria.euro_min_class_limit:
            return False

        if self.emission_type == EmissionType.NEDC:
            return self.emission <= le_criteria.nedc_max_emission_limit

        if self.emission_type == EmissionType.WLTP:
            return self.emission <= le_criteria.wltp_max_emission_limit

        return False

    class Meta:
        verbose_name = _("Vehicle")
        verbose_name_plural = _("Vehicles")

    def __str__(self):
        return "%s (%s, %s)" % (
            self.registration_number,
            self.manufacturer,
            self.model,
        )
