from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .mixins import TimestampedModelMixin


class ParkingPermitExtensionRequestQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=self.model.Status.PENDING)


class ParkingPermitExtensionRequest(TimestampedModelMixin):
    """Manages state for handling permit extension requests.

    When permit extension is requested, an instance should be created with
    the number of months. On approval on payment, the permit end date and month count
    should be incremented by this month count.
    """

    class Status(models.TextChoices):
        PENDING = _("Pending")
        APPROVED = _("Approved")
        REJECTED = _("Rejected")

    permit = models.ForeignKey(
        "parking_permits.ParkingPermit",
        on_delete=models.PROTECT,
        related_name="permit_extension_requests",
    )

    order = models.ForeignKey(
        "parking_permits.Order",
        on_delete=models.PROTECT,
        related_name="permit_extension_requests",
    )

    month_count = models.PositiveIntegerField(validators=[MaxValueValidator(12)])

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )

    status_changed_at = models.DateTimeField(null=True, blank=True)

    objects = ParkingPermitExtensionRequestQuerySet.as_manager()

    def __str__(self):
        return f"{self.permit_id}:{self.get_status_display()}"

    def is_approved(self):
        return self.status == self.Status.APPROVED

    def is_rejected(self):
        return self.status == self.Status.REJECTED

    def is_pending(self):
        return self.status == self.Status.PENDING

    def approve(self):
        self.set_status(self.Status.APPROVED)
        self.permit.extend_permit(self.month_count)

    def reject(self):
        self.set_status(self.Status.REJECTED)

    def set_status(self, new_status, commit=True):
        self.status = new_status
        self.status_changed_at = timezone.now()
        if commit:
            self.save()
