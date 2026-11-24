from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from parking_permits.models import ParkingPermit, Refund, Subscription
from parking_permits.models.order import (
    Order,
    OrderStatus,
    OrderType,
    SubscriptionCancelReason,
)
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


@transaction.atomic
def end_permits(
    user: User | None,
    *permits: ParkingPermit,
    iban: str | None = None,
    end_type: ParkingPermitEndType,
    **kwargs,
) -> None:
    """
    Ends all permits.

    Will first issue refunds for fixed period permits, then end each permit.

    Any refunds should be created for the permits if applicable.

    For each ended permit, will sync with Parkkihubi
    and send relevant customer emails and
    create relevant events.
    """

    permit_ids = [permit.pk for permit in permits]
    # Ending may cancel orders. Match payment processing's order-before-permit
    # locks without blocking foreign-key references from a concurrent price change.
    list(
        Order.objects.filter(permits__in=permit_ids)
        .select_for_update(of=("self",), no_key=True)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    locked_permits = {
        permit.pk: permit
        for permit in ParkingPermit.objects.select_for_update()
        .filter(pk__in=permit_ids)
        .order_by("pk")
    }
    # The caller can require secondary permits to end before the primary.
    permits = tuple(locked_permits[pk] for pk in permit_ids)

    create_permit_refunds(
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


def price_change_total(changes):
    return sum(
        line["price_change"] * line["month_count"]
        for lines in changes.values()
        for line in lines
    )


def _net_refund_amounts(credits):
    """Offset debits before issuing positive refund amounts."""
    debit = -sum(amount for amount in credits.values() if amount < 0)
    for key, credit in credits.items():
        if credit > 0:
            offset = min(debit, credit)
            debit -= offset
            if credit > offset:
                yield key, credit - offset


def apply_prepaid_price_change(customer, changes, user, iban, description):
    """Record signed changes to prepaid months and refund the net credit."""
    if not any(changes.values()):
        return
    Order.objects.create_renewal_order(
        customer,
        status=OrderStatus.CONFIRMED,
        order_type=OrderType.PRICE_ADJUSTED,
        price_changes=changes,
        user=user,
    )
    groups = defaultdict(Decimal)
    permits = defaultdict(set)
    for lines in changes.values():
        for line in lines:
            key = (line["funding_order"], line["price_change_vat_percent"] / 100)
            groups[key] -= line["price_change"] * line["month_count"]
            permits[key].add(line["source_item"].permit_id)
    for key, credit in _net_refund_amounts(groups):
        order, vat = key
        create_refund(
            user=user,
            permits=list(ParkingPermit.objects.filter(pk__in=permits[key])),
            orders=[order],
            amount=credit,
            vat=vat,
            iban=iban or "",
            description=description,
        )


def create_permit_refunds(
    user: User | None,
    *permits: ParkingPermit,
    iban: str | None,
) -> list[Refund]:
    """Creates VAT-based summary refunds from the permits provided.

    If refunds are created, then will send refund receipt email to customer
    and create the relevant events.

    If OPEN ENDED permits, the Refund will always be None:
       refunds are issued for open-ended
    permits when cancelling the subscription (see `end_permit()`).

    Returns the created refund instances, or empty list if not available.
    """
    refundable_permits = [permit for permit in permits if permit.can_be_refunded]
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

    amounts = {vat: data["total"] for vat, data in total_sums_per_vat.items()}
    for vat, credit in _net_refund_amounts(amounts):
        refunds.append(
            create_refund(
                user=user,
                permits=refundable_permits,
                orders=list(total_sums_per_vat[vat]["orders"]),
                amount=credit,
                iban=iban,
                vat=vat,
            )
        )
    if refunds:
        for data in total_sums_per_vat.values():
            for order_item in data["order_items"]:
                order_item.is_refunded = True
                order_item.save()

    return refunds


def create_refund(
    user: User | None,
    permits: list[ParkingPermit],
    orders: list[Order],
    amount: Decimal,
    iban: str | None,
    vat: Decimal = DEFAULT_VAT,
    description: str | None = "",
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
            else f"Refund for ending permits "
            f"{','.join([str(permit.id) for permit in permits])}"
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
    user: User | None,
    permit: ParkingPermit,
    end_type: ParkingPermitEndType,
    *,
    iban: str | None = None,
    subscription_cancel_reason: SubscriptionCancelReason = SubscriptionCancelReason.USER_CANCELLED,  # noqa: E501
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
        # Cancel fixed period permit order when this
        # is the last valid permit in that order
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
