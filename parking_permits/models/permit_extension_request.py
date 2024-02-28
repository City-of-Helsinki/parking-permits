from dateutil.relativedelta import relativedelta
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .mixins import TimestampedModelMixin


class ParkingPermitExtensionRequestQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=self.model.Status.PENDING)

    def cancel_pending(self):
        """Cancels any PENDING requests in queryset."""
        return self.pending().update(
            status=self.model.Status.CANCELLED, status_changed_at=timezone.now()
        )


class ParkingPermitExtensionRequest(TimestampedModelMixin):
    """Manages state for handling permit extension requests.

    When permit extension is requested, an instance should be created with
    the number of months. On approval on payment, the permit end date and month count
    should be incremented by this month count.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        APPROVED = "APPROVED", _("Approved")
        CANCELLED = "CANCELLED", _("Cancelled")

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

    def is_pending(self):
        return self.status == self.Status.PENDING

    def is_cancelled(self):
        return self.status == self.Status.CANCELLED

    def get_end_time(self):
        return (
            self.permit.end_time + relativedelta(months=self.month_count)
            if self.permit.end_time
            else None
        )

    @property
    def extension_range(self):
        return self.permit.end_time, self.get_end_time()

    def approve(self):
        self.set_status(self.Status.APPROVED)
        self.permit.extend_permit(self.month_count)

    def cancel(self):
        self.set_status(self.Status.CANCELLED)

    def set_status(self, new_status, commit=True):
        self.status = new_status
        self.status_changed_at = timezone.now()
        if commit:
            self.save()
