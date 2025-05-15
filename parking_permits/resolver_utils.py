from decimal import Decimal
from typing import Optional

from parking_permits.models import ParkingPermit, Refund, Subscription
from parking_permits.models.order import Order, SubscriptionCancelReason
from users.models import User

from .constants import DEFAULT_VAT
from .models.parking_permit import (
    ParkingPermitEndType,
    ParkingPermitEventFactory,
    ParkingPermitStatus,
)
from .services.mail import (
    PermitEmailType,
    send_permit_email,
    send_vehicle_low_emission_discount_email,
)
from .services.parkkihubi import sync_with_parkkihubi


def end_permits(
    user: Optional[User],
    *permits: ParkingPermit,
    iban: Optional[str] = None,
    end_type: ParkingPermitEndType,
    **kwargs,
) -> None:
    """
    Ends all permits.

    Will first issue refunds for fixed period permits, then end each permit.

    Any refunds should be created for the permits if applicable.

    For each ended permit, will sync with Parkkihubi and send relevant customer emails and
    create relevant events.
    """

    create_fixed_period_refunds(
        user,
        *permits,
        iban=iban,
    )

    for permit in permits:
        end_permit(
            user,
            permit,
            end_type,
            iban=iban,
            **kwargs,
        )


def create_fixed_period_refunds(
    user: Optional[User],
    *permits: ParkingPermit,
    iban: Optional[str],
) -> list[Refund]:
    """Creates VAT-based summary refunds from the permits provided.

    If refunds are created, then will send refund receipt email to customer
    and create the relevant events.

    If OPEN ENDED permits, the Refund will always be None: refunds are issued for open-ended
    permits when cancelling the subscription (see `end_permit()`).

    Returns the created refund instances, or empty list if not available.
    """
    refundable_permits = [
        permit
        for permit in permits
        if permit.can_be_refunded and permit.is_fixed_period
    ]
    if not refundable_permits:
        return []

    refunds = []

    total_sums_per_vat = {}

    for permit in refundable_permits:
        data_per_vat = permit.get_vat_based_refund_amounts_for_unused_items()
        for vat, vat_data in data_per_vat.items():
            if vat not in total_sums_per_vat:
                total_sums_per_vat[vat] = {
                    "total": Decimal(0),
                    "orders": set(),
                    "order_items": set(),
                }
            total_sums_per_vat[vat]["total"] += vat_data.get("total") or Decimal(0)
            total_sums_per_vat[vat]["orders"].update(vat_data.get("orders"))
            total_sums_per_vat[vat]["order_items"].update(vat_data.get("order_items"))

    total_sum = sum([vat["total"] for vat in total_sums_per_vat.values()])

    if total_sum > 0:
        refunds = []
        for vat, data in total_sums_per_vat.items():
            refunds.append(
                create_refund(
                    user=user,
                    permits=refundable_permits,
                    orders=list(data["orders"]),
                    amount=data["total"],
                    iban=iban,
                    vat=vat,
                )
            )
            # mark the order items as refunded
            for order_item in data["order_items"]:
                order_item.is_refunded = True
                order_item.save()

    return refunds


def create_refund(
    user: Optional[User],
    permits: list[ParkingPermit],
    orders: list[Order],
    amount: Decimal,
    iban: Optional[str],
    vat: Decimal = DEFAULT_VAT,
    description: Optional[str] = "",
) -> Refund:
    """
    Creates refund for permits and create relevant events.

    Returns the created refund instance.
    """
    refund = Refund.objects.create(
        name=permits[0].customer.full_name,
        amount=abs(amount),
        iban=iban,
        vat=vat,
        description=(
            description
            if description
            else f"Refund for ending permits {','.join([str(permit.id) for permit in permits])}"
        ),
    )
    refund.permits.add(*permits)
    refund.orders.add(*orders)

    for permit in permits:
        ParkingPermitEventFactory.make_create_refund_event(
            permit, refund, created_by=user
        )

    return refund


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

    Parkkihubi is updated with new status.

    Any active temporary vehicles are deactivated in permit.end_permit()
    if end_type in [IMMEDIATELY, PREVIOUS_DAY_END]
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
        for order in permit.orders.all():
            if (
                order
                and not order.order_permits.filter(status=ParkingPermitStatus.VALID)
                .exclude(pk=permit.pk)
                .exists()
            ):
                order.cancel(cancel_from_talpa=cancel_from_talpa)

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
