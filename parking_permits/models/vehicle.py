from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _

from .mixins import TimestampedModelMixin


class VehicleClass(models.TextChoices):
    M1 = "M1", _("M1")
    M1G = "M1G", _("M1G")
    M2 = "M2", _("M2")
    N1 = "N1", _("N1")
    N1G = "N1G", _("N1G")
    N2 = "N2", _("N2")
    N2G = "N2G", _("N2G")
    L3e = "L3e", _("L3e")
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


def is_low_emission_vehicle(power_type, euro_class, emission_type, emission):
    if power_type.is_electric:
        return True
    try:
        now = tz.now()
        le_criteria = LowEmissionCriteria.objects.get(
            start_date__lte=now,
            end_date__gte=now,
        )
    except LowEmissionCriteria.DoesNotExist:
        return False

    if (
        not euro_class
        or emission in (None, 0)
        or euro_class < le_criteria.euro_min_class_limit
    ):
        return False

    if emission_type == EmissionType.NEDC:
        return emission <= le_criteria.nedc_max_emission_limit

    if emission_type == EmissionType.WLTP:
        return emission <= le_criteria.wltp_max_emission_limit

    return False


class VehiclePowerType(models.Model):
    name = models.CharField(_("Name"), max_length=100, null=True, blank=True)
    identifier = models.CharField(_("Identifier"), max_length=10)

    class Meta:
        verbose_name = _("Vehicle power type")
        verbose_name_plural = _("Vehicle power types")

    def __str__(self):
        return "Identifier: %s, Name: %s" % (
            self.identifier,
            self.name,
        )

    @property
    def is_electric(self):
        return self.identifier == "04"


class LowEmissionCriteria(TimestampedModelMixin):
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
        return "NEDC: %s, WLTP: %s, EURO: %s" % (
            self.nedc_max_emission_limit,
            self.wltp_max_emission_limit,
            self.euro_min_class_limit,
        )


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
    euro_class = models.IntegerField(_("Euro class"), blank=True, null=True)
    emission = models.IntegerField(_("Emission"), blank=True, null=True)
    consent_low_emission_accepted = models.BooleanField(default=False)
    _is_low_emission = models.BooleanField(default=False, editable=False)
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
    updated_from_traficom_on = models.DateField(
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

    def save(self, *args, **kwargs):
        self._is_low_emission = self.is_low_emission
        super(Vehicle, self).save(*args, **kwargs)

    @property
    def is_low_emission(self):
        return is_low_emission_vehicle(
            self.power_type,
            self.euro_class,
            self.emission_type,
            self.emission,
        )

    @property
    def description(self):
        return f'{_("Vehicle")}: {str(self)}'

    def __str__(self):
        vehicle_str = "%s" % self.registration_number or ""
        if self.manufacturer:
            vehicle_str += " (%s" % self.manufacturer
            if self.model:
                vehicle_str += ", %s" % self.model
            vehicle_str += ")"
        return vehicle_str
