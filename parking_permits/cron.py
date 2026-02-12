import logging

from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.utils import timezone as tz

from parking_permits.customer_permit import CustomerPermit
from parking_permits.exceptions import CustomerCannotBeAnonymizedError
from parking_permits.models import (
    Announcement,
    Customer,
    ParkingPermit,
)
from parking_permits.models.order import SubscriptionCancelReason
from parking_permits.models.parking_permit import (
    ContractType,
    ParkingPermitEndType,
    ParkingPermitStatus,
)
from parking_permits.services.mail import (
    PermitEmailType,
    send_announcement_emails,
    send_permit_email,
)
from parking_permits.services.parkkihubi import sync_with_parkkihubi

logger = logging.getLogger("django")
db_logger = logging.getLogger("db")


def handle_announcement_emails():
    announcements = Announcement.objects.filter(emails_handled=False)
    logger.info(f"Found unhandled announcements: {announcements.count()}")
    for announcement in announcements:
        customers = Customer.objects.filter(
            permits__parking_zone__in=announcement.parking_zones.all(),
            permits__status=ParkingPermitStatus.VALID,
        ).distinct()
        logger.info(
            f"Found {customers.count()} customers for announcement {announcement.pk}"
        )
        send_announcement_emails(customers, announcement)
        announcement.emails_handled = True
        announcement.save()
        logger.info(f"Announcement {announcement.pk} emails handled")


def automatic_expiration_of_permits():
    logger.info("Automatically ending permits started...")
    now = tz.localtime(tz.now())
    ending_permits = ParkingPermit.objects.filter(
        Q(end_time__lt=now)
        | Q(vehicle_changed=True, vehicle_changed_date__lt=now.date())
        | Q(address_changed=True, address_changed_date__lt=now.date()),
        status=ParkingPermitStatus.VALID,
    )
    for permit in ending_permits:
        CustomerPermit(permit.customer_id).end(
            [permit.id],
            ParkingPermitEndType.PREVIOUS_DAY_END,
            iban="",
            subscription_cancel_reason=SubscriptionCancelReason.PERMIT_EXPIRED,
            cancel_from_talpa=True,
            force_end=True,
        )
        # If the customer has only one permit left, make it primary
        active_permits = permit.customer.permits.active()
        if active_permits.count() == 1:
            active_permit = active_permits.first()
            active_permit.primary_vehicle = True
            active_permit.save()
        logger.info(f"Permit {permit.pk} ended")

    logger.info("Automatically ending permits completed.")


def automatic_expiration_remind_notification_of_permits():
    logger.info("Automatically sending remind notifications for permits started...")
    count = 0
    current_date = tz.localdate(tz.now())
    expiring_permits = ParkingPermit.objects.filter(
        Q(end_time__date=current_date + relativedelta(weeks=1))
        | Q(end_time__date=current_date + relativedelta(days=1)),
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.FIXED_PERIOD,
    )
    for permit in expiring_permits:
        success = send_permit_email(PermitEmailType.EXPIRATION_REMIND, permit)
        if success:
            count += 1
    logger.info(
        "Automatically sending remind notifications for permits completed. "
        f"{count} notifications sent."
    )
    return expiring_permits


def automatic_remove_obsolete_customer_data():
    db_logger.info("Automatic anonymization of obsolete customer data started...")

    # Pre-filter candidates at database level to reduce Python iteration
    # Exclude customers with valid permits and those modified recently
    now = tz.localdate(tz.now())
    cutoff_time = now - relativedelta(years=2)

    candidates = (
        Customer.objects.filter(is_anonymized=False, modified_at__lt=cutoff_time)
        .exclude(permits__status=ParkingPermitStatus.VALID)
        .prefetch_related(
            "permits"  # Prefetch for can_be_anonymized check
        )
    )

    count = 0
    for customer in candidates:
        try:
            customer.anonymize_all_data()
        except CustomerCannotBeAnonymizedError:
            continue
        count += 1

    db_logger.info(
        "Automatic anonymization of obsolete customer data completed. "
        f"{count} customers are anonymized."
    )


def automatic_syncing_of_permits_to_parkkihubi():
    logger.info("Automatically syncing permits to Parkkihubi started...")

    # Automatically deactivate temporary vehicles that are in the past
    # for valid permits
    temp_vehicle_permits = ParkingPermit.objects.filter(
        status=ParkingPermitStatus.VALID,
        temp_vehicles__is_active=True,
        temp_vehicles__end_time__lt=tz.localtime(tz.now()),
    )
    for permit in temp_vehicle_permits:
        permit.remove_temporary_vehicle()
        sync_with_parkkihubi(permit)
        send_permit_email(PermitEmailType.TEMP_VEHICLE_DEACTIVATED, permit)
        logger.info(
            f"Permit {permit.pk} temporary vehicle deactivated "
            f"because it is in the past."
        )

    statuses_to_sync = [
        ParkingPermitStatus.CLOSED,
        ParkingPermitStatus.VALID,
    ]
    permits = ParkingPermit.objects.filter(
        synced_with_parkkihubi=False, status__in=statuses_to_sync
    )
    permit_count = permits.count()
    for permit in permits:
        sync_with_parkkihubi(permit)

    logger.info(
        "Automatically syncing permits to Parkkihubi completed. "
        f"{permit_count} permits synced."
    )
