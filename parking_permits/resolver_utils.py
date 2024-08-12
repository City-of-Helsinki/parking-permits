from typing import Optional, Tuple

from parking_permits.constants import DEFAULT_VAT
from parking_permits.models import Order, ParkingPermit, Refund, Subscription
from parking_permits.models.order import (
    OrderPaymentType,
    OrderStatus,
    OrderType,
    SubscriptionCancelReason,
)
from users.models import User

from .models.parking_permit import (
    ParkingPermitEndType,
    ParkingPermitEventFactory,
    ParkingPermitStatus,
)
from .services.mail import (
    PermitEmailType,
    RefundEmailType,
    send_permit_email,
    send_refund_email,
    send_vehicle_low_emission_discount_email,
)
from .services.parkkihubi import sync_with_parkkihubi


def end_permits(
    user: Optional[User],
    *permits: ParkingPermit,
    iban: Optional[str] = None,
    end_type: ParkingPermitEndType,
    payment_type: OrderPaymentType,
    **kwargs,
) -> None:
    """
    Ends all permits.

    Will first issue refunds for fixed period permits, then end each permit.

    Any refunds should be created for the permits if applicable.

    For each ended permit, will sync with Parkkihubi and send relevant customer emails and
    create relevant events.
    """

    create_fixed_period_refund(
        user,
        *permits,
        iban=iban,
        payment_type=payment_type,
    )

    for permit in permits:
        end_permit(
            user,
            permit,
            end_type,
            iban=iban,
            **kwargs,
        )


def create_fixed_period_refund(
    user: Optional[User],
    *permits: ParkingPermit,
    iban: Optional[str],
    payment_type: OrderPaymentType,
) -> Tuple[Optional[Refund], bool]:
    """Creates a refund model from the permits provided.

    If refund is created, then will send refund receipt email to customer
    and create the relevant event.

    If OPEN ENDED permits, the Refund will always be None: refunds are issued for open-ended
    permits when cancelling the subscription (see `end_permit()`).

    Returns the Refund instance, or None if not available, and True or False if refund is created.
    """
    refundable_permits = [
        permit
        for permit in permits
        if permit.can_be_refunded and permit.is_fixed_period
    ]
    if not refundable_permits:
        return None, False

    first_permit = refundable_permits[0]
    latest_order = first_permit.latest_order
    customer = first_permit.customer

    created = False

    if refund := Refund.objects.filter(order=latest_order).first():
        order = Order.objects.create_renewal_order(
            first_permit.customer,
            status=OrderStatus.CONFIRMED,
            order_type=OrderType.CREATED,
            payment_type=payment_type,
            iban=iban,
            user=user,
            create_renew_order_event=False,
        )
        total_sum = order.total_price
        order.order_items.all().delete()

    else:
        total_sum = sum(
            [
                permit.get_refund_amount_for_unused_items()
                for permit in refundable_permits
            ]
        )
        order = latest_order

    if total_sum > 0:
        refund = Refund.objects.create(
            name=customer.full_name,
            order=order,
            amount=total_sum,
            iban=iban,
            vat=(
                order.order_items.first().vat
                if order.order_items.exists()
                else DEFAULT_VAT
            ),
            description=f"Refund for ending permits {','.join([str(permit.id) for permit in permits])}",
        )
        refund.permits.set(permits)
        send_refund_email(RefundEmailType.CREATED, customer, [refund])

        for permit in permits:
            ParkingPermitEventFactory.make_create_refund_event(
                permit, refund, created_by=user
            )

        created = True
    return refund, created


def end_permit(
    user: Optional[User],
    permit: ParkingPermit,
    end_type: ParkingPermitEndType,
    *,
    iban: Optional[str] = None,
    subscription_cancel_reason: SubscriptionCancelReason = SubscriptionCancelReason.USER_CANCELLED,
    cancel_from_talpa: bool = True,
    force_end: bool = False,
) -> None:
    """
    Handles ending permit functionality.

    Ends Subscription for open ended permit and issues refund if applicable.

    Any active temporary vehicles are deactivated.

    Parkkihubi is updated with new status.
    """
    if permit.is_open_ended:
        if subscription := (
            Subscription.objects.filter(order_items__permit__pk=permit.pk)
            .distinct()
            .first()
        ):
            subscription.cancel(
                cancel_reason=subscription_cancel_reason,
                cancel_from_talpa=cancel_from_talpa,
                iban=iban or "",
            )
    else:
        # Cancel fixed period permit order when this is the last valid permit in that order
        latest_order = permit.latest_order
        if (
            latest_order
            and not latest_order.order_permits.filter(status=ParkingPermitStatus.VALID)
            .exclude(pk=permit.pk)
            .exists()
        ):
            latest_order.cancel(cancel_from_talpa=cancel_from_talpa)

    permit.temp_vehicles.update(is_active=False)

    if permit.consent_low_emission_accepted and permit.vehicle.is_low_emission:
        send_vehicle_low_emission_discount_email(
            PermitEmailType.VEHICLE_LOW_EMISSION_DISCOUNT_DEACTIVATED,
            permit,
        )

    permit.end_permit(end_type, force_end=force_end)

    sync_with_parkkihubi(permit)

    permit.refresh_from_db()

    send_permit_email(PermitEmailType.ENDED, permit)

    ParkingPermitEventFactory.make_end_permit_event(permit, created_by=user)
