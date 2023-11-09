import datetime
import logging

from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.utils import timezone as tz

from parking_permits.constants import ParkingPermitEndType
from parking_permits.customer_permit import CustomerPermit
from parking_permits.exceptions import ParkkihubiPermitError
from parking_permits.models import Customer, ParkingPermit
from parking_permits.models.order import SubscriptionCancelReason
from parking_permits.models.parking_permit import ParkingPermitStatus
from parking_permits.services.mail import PermitEmailType, send_permit_email

logger = logging.getLogger("django")
db_logger = logging.getLogger("db")


def automatic_expiration_of_permits():
    logger.info("Automatically ending permits started...")
    now = tz.localtime(tz.now())
    ending_permits = ParkingPermit.objects.filter(
        Q(end_time__lt=now)
        | Q(vehicle_changed=True, vehicle_changed_date__lt=now.date()),
        status=ParkingPermitStatus.VALID,
    )
    for permit in ending_permits:
        CustomerPermit(permit.customer_id).end(
            [permit.id],
            ParkingPermitEndType.IMMEDIATELY,
            iban="",
            subscription_cancel_reason=SubscriptionCancelReason.PERMIT_EXPIRED,
            cancel_from_talpa=True,
            force_end=True,
        )
        permit.refresh_from_db()
        # Set end time to end of the day
        permit.end_time = permit.end_time.replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=999999,
            tzinfo=datetime.timezone.utc,
        )
        permit.save()
        # If the customer has only one permit left, make it primary
        active_permits = permit.customer.permits.active()
        if active_permits.count() == 1:
            active_permit = active_permits.first()
            active_permit.primary_vehicle = True
            active_permit.save()

    logger.info("Automatically ending permits completed.")


def automatic_expiration_remind_notification_of_permits():
    logger.info("Automatically sending remind notifications for permits started...")
    count = 0
    now = tz.localdate(tz.now())
    expiring_permits = ParkingPermit.objects.filter(
        end_time__lt=now + relativedelta(weeks=1), status=ParkingPermitStatus.VALID
    )
    for permit in expiring_permits:
        send_permit_email(PermitEmailType.EXPIRATION_REMIND, permit)
        count += 1
    logger.info(
        "Automatically sending remind notifications for permits completed. "
        f"{count} notifications sent."
    )
    return expiring_permits


def automatic_remove_obsolete_customer_data():
    db_logger.info("Automatically removing obsolete customer data started...")
    qs = Customer.objects.all()
    count = 0
    for customer in qs:
        if customer.can_be_deleted:
            customer.delete_all_data()
            count += 1
    db_logger.info(
        "Automatically removing obsolete customer data completed. "
        f"{count} customers are removed."
    )


def automatic_syncing_of_permits_to_parkkihubi():
    statuses_to_sync = [
        ParkingPermitStatus.CLOSED,
        ParkingPermitStatus.VALID,
        ParkingPermitStatus.ACCEPTED,
        ParkingPermitStatus.REJECTED,
    ]
    permits = ParkingPermit.objects.filter(
        synced_with_parkkihubi=False, status__in=statuses_to_sync
    )
    for permit in permits:
        try:
            permit.update_parkkihubi_permit()
        except ParkkihubiPermitError:
            permit.create_parkkihubi_permit()
