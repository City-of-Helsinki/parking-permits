import logging
import re
from datetime import datetime

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.gis.db import models
from django.db.models.functions import Length
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from helsinki_gdpr.models import SerializableMixin

from ..services.traficom import Traficom
from .common import SourceSystem
from .driving_licence import DrivingLicence
from .mixins import TimestampedModelMixin
from .parking_permit import ParkingPermit, ParkingPermitStatus

logger = logging.getLogger("db")


class Languages(models.TextChoices):
    FINNISH = "fi", _("Finnish")
    SWEDISH = "sv", _("Swedish")
    ENGLISH = "en", _("English")


class Customer(SerializableMixin, TimestampedModelMixin):
    source_system = models.CharField(
        _("Source system"), max_length=50, choices=SourceSystem.choices, blank=True
    )
    source_id = models.CharField(_("Source id"), max_length=100, blank=True)
    user = models.OneToOneField(
        get_user_model(),
        related_name="customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    first_name = models.CharField(_("First name"), max_length=32, blank=True)
    last_name = models.CharField(_("Last name"), max_length=32, blank=True)
    national_id_number = models.CharField(
        _("National identification number"),
        max_length=50,
        null=True,
        blank=True,
        unique=True,
    )
    primary_address = models.ForeignKey(
        "Address",
        verbose_name=_("Primary address"),
        on_delete=models.PROTECT,
        related_name="customers_primary_address",
        null=True,
        blank=True,
    )
    primary_address_apartment = models.CharField(
        _("Primary address apartment"), max_length=32, blank=True, null=True
    )
    primary_address_apartment_sv = models.CharField(
        _("Primary address apartment (sv)"), max_length=32, blank=True, null=True
    )
    other_address = models.ForeignKey(
        "Address",
        verbose_name=_("Other address"),
        on_delete=models.PROTECT,
        related_name="customers_other_address",
        blank=True,
        null=True,
    )
    other_address_apartment = models.CharField(
        _("Other address apartment"), max_length=32, blank=True, null=True
    )
    other_address_apartment_sv = models.CharField(
        _("Other address apartment (sv)"), max_length=32, blank=True, null=True
    )
    email = models.CharField(_("Email"), max_length=128, blank=True)
    phone_number = models.CharField(
        _("Phone number"), max_length=32, blank=True, null=True
    )
    address_security_ban = models.BooleanField(_("Address security ban"), default=False)
    driver_license_checked = models.BooleanField(
        _("Driver's license checked"), default=False
    )
    zone = models.ForeignKey(
        "ParkingZone",
        verbose_name=_("Zone"),
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    language = models.CharField(
        _("Language"),
        max_length=10,
        choices=Languages.choices,
        default=Languages.FINNISH,
    )

    serialize_fields = (
        {"name": "first_name"},
        {"name": "last_name"},
        {"name": "national_id_number"},
        {"name": "email"},
        {"name": "phone_number"},
        {"name": "primary_address", "accessor": lambda a: a.serialize() if a else None},
        {"name": "other_address", "accessor": lambda a: a.serialize() if a else None},
        {"name": "orders"},
        {"name": "permits"},
    )

    class Meta:
        verbose_name = _("Customer")
        verbose_name_plural = _("Customers")

    def __str__(self):
        return "%s" % self.national_id_number

    @property
    def full_name(self):
        return "%s %s" % (self.first_name, self.last_name)

    @full_name.setter
    def full_name(self, value):
        self._full_name = value

    @property
    def age(self):
        ssn = self.national_id_number
        key_centuries = {"+": "18", "-": "19", "A": "20"}
        date_of_birth = datetime(
            year=int(key_centuries[ssn[6]] + ssn[4:6]),
            month=int(ssn[2:4]),
            day=int(ssn[0:2]),
        )
        return relativedelta(datetime.today(), date_of_birth).years

    def fetch_vehicle_detail(self, registration_number):
        return Traficom().fetch_vehicle_details(registration_number)

    def is_user_of_vehicle(self, vehicle):
        if not settings.TRAFICOM_CHECK:
            return True
        users_nin = [user.national_id_number for user in vehicle.users.all()]
        return self.national_id_number in users_nin

    def fetch_driving_licence_detail(self):
        licence_details = Traficom().fetch_driving_licence_details(
            self.national_id_number
        )
        driving_licence = DrivingLicence.objects.update_or_create(
            customer=self,
            defaults={
                "start_date": licence_details.get("issue_date"),
            },
        )
        driving_classes = licence_details.get("driving_classes", [])
        driving_licence[0].driving_classes.set(driving_classes)
        return driving_licence

    def has_valid_driving_licence_for_vehicle(self, vehicle):
        if not settings.TRAFICOM_CHECK:
            return True
        return any(
            vehicle.vehicle_class in d_class.vehicle_classes
            for d_class in self.driving_licence.driving_classes.all()
        )

    @property
    def full_primary_address(self):
        return (
            f"{self.primary_address.street_name} {self.primary_address.street_number} "
            f"{self.primary_address_apartment}, "
            f"{self.primary_address.postal_code} {self.primary_address.city}"
            if self.primary_address
            else ""
        )

    @property
    def full_primary_address_sv(self):
        return (
            f"{self.primary_address.street_name_sv} {self.primary_address.street_number} "
            f"{self.primary_address_apartment_sv}, "
            f"{self.primary_address.postal_code} {self.primary_address.city_sv}"
            if self.primary_address
            else ""
        )

    @property
    def full_other_address(self):
        return (
            f"{self.other_address.street_name} {self.other_address.street_number} "
            f"{self.other_address_apartment}, "
            f"{self.other_address.postal_code} {self.other_address.city}"
            if self.other_address
            else ""
        )

    @property
    def full_other_address_sv(self):
        return (
            f"{self.other_address.street_name_sv} {self.other_address.street_number} "
            f"{self.other_address_apartment_sv}, "
            f"{self.other_address.postal_code} {self.other_address.city_sv}"
            if self.other_address
            else ""
        )

    @property
    def can_be_deleted(self):
        """
        Returns True if the customer and its data can be removed

        This property can be used to check if the deleting is allowed
        via GDPR API triggered from Helsinki Profile or automatic
        removal process. A customer that can be removed must satisfy
        following conditions:

        - The last modified time of the customer is more than 2 years ago
        - The customer does not have any valid permits
        - The latest permit must be ended and modified more than 2 years ago
        """
        now = timezone.now()
        time_delta = relativedelta(years=2)
        if self.modified_at + time_delta > now:
            return False

        has_valid_permits = self.permits.filter(
            status=ParkingPermitStatus.VALID
        ).exists()
        if has_valid_permits:
            return False

        try:
            latest_modified_at = self.permits.latest("modified_at").modified_at
            latest_end_time = self.permits.latest("end_time").end_time
            times = [latest_modified_at, latest_end_time]
            latest_time = max([time for time in times if time])
            if latest_time + time_delta > now:
                return False
        except ParkingPermit.DoesNotExist:
            pass

        return True

    def delete_all_data(self):
        """Delete all customer related data"""

        self.permits.all().delete()
        self.orders.all().delete()
        if self.user:
            self.user.delete()
        self.delete()

    @property
    def active_permits(self):
        return self.permits.active()


def generate_ssn():
    customer_qs = (
        Customer.objects.annotate(ssn_len=Length("national_id_number"))
        .filter(national_id_number__istartswith="XX-", ssn_len__gte=9)
        .order_by("-national_id_number")
    )
    if customer_qs.exists():
        for customer in customer_qs:
            latest_generated_ssn = customer.national_id_number
            match = re.search(r"\d+", latest_generated_ssn)
            if match:
                latest_generated_ssn_number = int(match.group()) + 1
                return "XX-%06d" % (latest_generated_ssn_number,)
    return "XX-000001"
