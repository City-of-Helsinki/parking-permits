import logging
import re
from datetime import datetime

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.gis.db import models
from django.db import transaction
from django.db.models.functions import Length
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from helsinki_gdpr.models import SerializableMixin

from parking_permits.exceptions import CustomerCannotBeAnonymizedError

from ..services.traficom import Traficom
from .common import SourceSystem
from .driving_licence import DrivingLicence
from .mixins import TimestampedModelMixin
from .parking_permit import ParkingPermit, ParkingPermitEvent, ParkingPermitStatus
from .refund import Refund
from .vehicle import VehicleUser

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
    first_name = models.CharField(_("First name"), max_length=64, blank=True)
    last_name = models.CharField(_("Last name"), max_length=64, blank=True)
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

    is_anonymized = models.BooleanField(
        _("Is anonymized"),
        default=False,
        help_text=_(
            "Indicates if customer data has been anonymized for GDPR compliance"
        ),
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
        return f"{self.national_id_number}"

    # NOTE about the static methods below:
    # - These are intended as DRY-helpers for larger queries
    # which may use these in annotate()-statements.
    # - customer_id_expression is intended to be either an
    # usual customer id OR an OuterRef-expression inside a subquery
    # referring to the customer-id field in its parent query.
    # - this is to keep practically identical queries maintainable
    # from one place. Queries are needed in multiple cases, as
    # the code ultimately using these has to check for the
    # presence of the prefetch-attributes and may need to fall back
    # to a "default" queryset.
    # - the above reason is also the reason for these being static
    # methods.

    @staticmethod
    def active_subscription_order_items(customer_id_expression):
        # Used as a base queryset to detect whether
        # the customer has any active subscriptions.
        # Exists()-check is done in the caller, see the note above.
        # Avoid circular imports.
        from parking_permits.models.order import OrderItem, SubscriptionStatus

        return OrderItem.objects.filter(
            order__customer_id=customer_id_expression,
            subscription__isnull=False,
            subscription__status=SubscriptionStatus.CONFIRMED,
        )

    @staticmethod
    def valid_permits(customer_id_expression):
        return ParkingPermit.objects.filter(
            status=ParkingPermitStatus.VALID,
            customer_id=customer_id_expression,
        )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

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

    def fetch_vehicle_detail(self, registration_number, permit=None):
        return Traficom().fetch_vehicle_details(registration_number, permit=permit)

    def is_user_of_vehicle(self, vehicle):
        if not settings.TRAFICOM_CHECK:
            return True
        users_nin = [user.national_id_number for user in vehicle.users.all()]
        return self.national_id_number in users_nin

    def fetch_driving_licence_detail(self, permit=None):
        licence_details = Traficom().fetch_driving_licence_details(
            self.national_id_number,
            permit=permit,
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
            f"{self.primary_address.street_name_sv} "
            f"{self.primary_address.street_number} "
            f"{self.primary_address_apartment_sv}, "
            f"{self.primary_address.postal_code} "
            f"{self.primary_address.city_sv}"
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
    def can_be_anonymized(self):
        """
        Returns True if the customer data can be anonymized for GDPR compliance.

        This property can be used to check if the anonymization is allowed
        via GDPR API triggered from Helsinki Profile or automatic
        removal process.

        Conditions:
        - The customer is not already anonymized
        - The last modified time of the customer is more than 2 years ago
        - The customer does not have any valid permits
        - The latest permit must be ended and modified more than 2 years ago
        - The customer must not have any active subscriptions
        """
        if self.is_anonymized:
            return False

        now = timezone.now()
        time_delta = relativedelta(years=2)
        if self.modified_at + time_delta > now:
            return False

        has_valid_permits = (
            self.prefetched_has_valid_permits
            if hasattr(self, "prefetched_has_valid_permits")
            else Customer.valid_permits(self.id).exists()
        )
        if has_valid_permits:
            return False

        try:
            latest_modified_at = (
                self.prefetched_latest_permit_modified_at
                if hasattr(self, "prefetched_latest_permit_modified_at")
                else self.permits.latest("modified_at").modified_at
            )
            latest_end_time = (
                self.prefetched_latest_permit_end_time
                if hasattr(self, "prefetched_latest_permit_end_time")
                else self.permits.latest("end_time").end_time
            )
            times = [latest_modified_at, latest_end_time]
            times = [time for time in times if time]
            if times:
                latest_time = max(times)
                if latest_time + time_delta > now:
                    return False
        except ParkingPermit.DoesNotExist:
            pass

        has_active_subscriptions = (
            self.prefetched_has_active_subscriptions
            if hasattr(self, "prefetched_has_active_subscriptions")
            else Customer.active_subscription_order_items(self.id).exists()
        )
        if has_active_subscriptions:
            return False

        return True

    def anonymize_all_data(self):
        """Anonymize all customer related data for GDPR compliance.

        Uses bulk operations to minimize database queries.
        """

        if not self.can_be_anonymized:
            raise CustomerCannotBeAnonymizedError

        with transaction.atomic():
            # Collect vehicles, these are needed for
            # VehicleUser-removal which in turn needs the
            # pre-anonymization national_id_number to allow removing
            # only those VehicleUsers that are linked to the customer.
            vehicle_ids_linked_to_permits = self.permits.values_list(
                "vehicle_id", flat=True
            ).union(
                self.permits.filter(next_vehicle_id__isnull=False).values_list(
                    "next_vehicle_id", flat=True
                )
            )

            # Delete VehicleUsers which are linked to these vehicles
            # and match the customers national_id_number.
            # Note that if vehicle_ids_linked_to_permits is empty,
            # then delete() is ran against an empty queryset => no-op.
            VehicleUser.objects.filter(
                vehicles__in=vehicle_ids_linked_to_permits,
                national_id_number=self.national_id_number,
            ).delete()

            # Anonymize Customer fields
            self.first_name = "Anonymized"
            self.last_name = "Customer"
            self.national_id_number = f"XX-ANON-{self.pk:06d}"
            self.email = ""
            self.phone_number = ""
            self.primary_address_apartment = ""
            self.primary_address_apartment_sv = ""
            self.other_address_apartment = ""
            self.other_address_apartment_sv = ""
            self.source_id = ""
            self.is_anonymized = True
            self.save()

            # Anonymize permits
            self.permits.update(
                address_apartment="",
                address_apartment_sv="",
                next_address_apartment="",
                next_address_apartment_sv="",
                description="",
            )

            # Anonymize orders
            self.orders.update(
                address_text="",
                talpa_checkout_url="",
                talpa_logged_in_checkout_url="",
                talpa_receipt_url="",
                talpa_update_card_url="",
            )

            # Anonymize refunds linked to permits/orders
            order_refunds = Refund.objects.filter(
                orders__in=self.orders.values_list("id", flat=True)
            )
            permit_refunds = Refund.objects.filter(
                permits__in=self.permits.values_list("id", flat=True)
            )
            linked_refunds = order_refunds.union(permit_refunds)

            refunds_to_update = []
            for refund in linked_refunds:
                refund.name = ""
                refund.iban = ""
                refund.description = ""
                refunds_to_update.append(refund)

            Refund.objects.bulk_update(
                refunds_to_update,
                fields=["name", "iban", "description"],
                batch_size=5000,
            )

            # Delete DrivingLicence (contains no statistical value)
            if hasattr(self, "driving_licence"):
                self.driving_licence.delete()

            # Anonymize User if exists
            if self.user:
                self.user.first_name = ""
                self.user.last_name = ""
                self.user.email = f"anonymized-{self.pk}@anonymized.invalid"
                self.user.username = f"anonymized-{self.pk}"
                self.user.save()

            # Clear Order.vehicles ArrayField (denormalized registration numbers)
            self.orders.update(vehicles=[])

            # Anonymize Company if customer is owner
            self.company_set.update(
                name=f"Anonymized Company {self.pk}", business_id=f"ANON-{self.pk:07d}"
            )

            # Clear ParkingPermitEvent.context where it may contain PII
            # The 'changes' key in context may contain customer field values
            # We clear context entirely for this customer's permit events
            # to be safe - IDs are still in the message field
            permit_events = ParkingPermitEvent.objects.filter(
                parking_permit_id__in=self.permits.values_list("id", flat=True)
            )

            permit_events.update(context={})

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
                return f"XX-{latest_generated_ssn_number:06d}"
    return "XX-000001"
