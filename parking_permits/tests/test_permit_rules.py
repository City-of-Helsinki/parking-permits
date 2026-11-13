from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from freezegun import freeze_time

from parking_permits.customer_permit import CustomerPermit
from parking_permits.exceptions import (
    ParkingPermitValidationError,
    PermitCanNotBeExtendedError,
)
from parking_permits.models import Order, ParkingPermit
from parking_permits.permit_rules import validate_secondary_permit
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.vehicle import VehicleFactory
from parking_permits.utils import get_end_time

HELSINKI = ZoneInfo("Europe/Helsinki")


def dt(value):
    return datetime.fromisoformat(value).replace(tzinfo=HELSINKI)


def permit(start, months=1, primary=True, **kwargs):
    start = dt(start)
    return ParkingPermit(
        start_time=start,
        month_count=months,
        end_time=get_end_time(start, months),
        primary_vehicle=primary,
        contract_type="FIXED_PERIOD",
        **kwargs,
    )


@pytest.mark.parametrize(
    "start,months,allowed",
    [
        ("2026-11-12T14:00", 3, True),
        ("2026-11-13T00:00", 3, False),
        ("2026-11-13T00:00", 2, True),
        ("2027-01-12T23:59", 1, True),
        ("2027-01-13T00:00", 1, False),
    ],
)
def test_purchase_duration(start, months, allowed):
    primary = permit("2026-11-12T12:00", 3)
    secondary = permit(start, months, False)
    if allowed:
        validate_secondary_permit(secondary, primary, purchase=True, now=dt(start))
    else:
        with pytest.raises(ParkingPermitValidationError):
            validate_secondary_permit(secondary, primary, purchase=True, now=dt(start))


@pytest.mark.parametrize(
    "start", ["2024-01-31T12:00", "2026-03-29T12:00", "2026-10-25T12:00"]
)
def test_month_end_and_dst(start):
    primary = permit(start)
    secondary = permit(start, primary=False)
    validate_secondary_permit(secondary, primary, purchase=True, now=dt(start))
    secondary.end_time += timedelta(microseconds=1)
    with pytest.raises(ParkingPermitValidationError):
        validate_secondary_permit(secondary, primary)


def test_earlier_start_is_rejected_even_for_subscription():
    primary = permit("2026-11-13T12:00")
    primary.contract_type = "OPEN_ENDED"
    secondary = permit("2026-11-12T12:00", primary=False)
    with pytest.raises(ParkingPermitValidationError, match="start before"):
        validate_secondary_permit(secondary, primary)


def test_subscription_renewal_date_is_not_a_limit_but_termination_is():
    primary = permit("2026-11-12T12:00")
    primary.contract_type = "OPEN_ENDED"
    secondary = permit("2026-11-12T13:00", 3, False)
    validate_secondary_permit(secondary, primary, purchase=True)
    primary.end_type = "AFTER_CURRENT_PERIOD"
    with pytest.raises(ParkingPermitValidationError):
        validate_secondary_permit(secondary, primary, purchase=True)


@pytest.mark.django_db
@freeze_time("2026-11-12T12:00:00+02:00")
def test_create_secondary_and_reject_next_day(settings):
    settings.TRAFICOM_CHECK = False
    primary = ParkingPermitFactory(
        status="VALID",
        contract_type="FIXED_PERIOD",
        start_time=timezone.now(),
        end_time=get_end_time(timezone.now(), 1),
        month_count=1,
    )
    customer = primary.customer
    primary.address = customer.primary_address
    primary.save()
    vehicle = VehicleFactory()
    with patch.object(type(customer), "fetch_vehicle_detail", return_value=vehicle):
        secondary = CustomerPermit(customer.pk).create(
            customer.primary_address_id, vehicle.registration_number
        )
        assert secondary.end_time == primary.end_time
        secondary.delete()
        with freeze_time("2026-11-13T00:00:00+02:00"):
            with pytest.raises(ParkingPermitValidationError):
                CustomerPermit(customer.pk).create(
                    customer.primary_address_id, vehicle.registration_number
                )
    assert ParkingPermit.objects.filter(customer=customer).count() == 1


@pytest.mark.django_db
@freeze_time("2026-11-12T12:00:00+02:00")
def test_stale_draft_cannot_be_ordered_and_update_cannot_start_before_primary():
    start = timezone.now()
    primary = ParkingPermitFactory(
        status="VALID",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=get_end_time(start, 1),
        month_count=1,
    )
    secondary = ParkingPermitFactory(
        customer=primary.customer,
        primary_vehicle=False,
        status="DRAFT",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=primary.end_time,
        month_count=1,
    )
    with pytest.raises(ParkingPermitValidationError):
        CustomerPermit(primary.customer_id).update(
            {"start_time": (start - timedelta(days=1)).isoformat()}, str(secondary.pk)
        )
    secondary.refresh_from_db()
    assert secondary.start_time == start
    with freeze_time("2026-11-13T00:00:00+02:00"):
        with pytest.raises(ParkingPermitValidationError):
            Order.objects.create_for_permits([secondary])
    assert not Order.objects.filter(customer=primary.customer).exists()


@pytest.mark.django_db
@freeze_time("2026-11-12T12:00:00+02:00")
def test_extension_limit_uses_the_date_actually_applied():
    start = dt("2026-10-31T12:00")
    primary = ParkingPermitFactory(
        status="VALID",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=get_end_time(start, 3),
        month_count=3,
    )
    secondary = ParkingPermitFactory(
        customer=primary.customer,
        primary_vehicle=False,
        status="VALID",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=get_end_time(start, 1),
        month_count=1,
    )
    assert secondary.max_extension_month_count == 2
    with pytest.raises(PermitCanNotBeExtendedError):
        Order.objects.create_for_extended_permit(secondary, 3)
    with pytest.raises(PermitCanNotBeExtendedError):
        list(secondary.get_price_list_for_extended_permit(month_count=3))
    secondary.extend_permit(2)
    secondary.refresh_from_db()
    assert secondary.end_time == primary.end_time
    with pytest.raises(PermitCanNotBeExtendedError):
        secondary.extend_permit(1)


@pytest.mark.django_db
@freeze_time("2026-11-12T12:00:00+02:00")
def test_admin_creation_and_extension_reject_invalid_dates(settings):
    # Exercise the resolver bodies; authentication is covered by resolver tests.
    import inspect

    from parking_permits.admin_resolvers import (
        resolve_create_resident_permit,
        resolve_extend_parking_permit,
    )

    settings.PERMIT_EXTENSIONS_ENABLED = True
    start = timezone.now()
    primary = ParkingPermitFactory(
        status="VALID",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=get_end_time(start, 1),
        month_count=1,
    )
    payload = {
        "customer": {"national_id_number": primary.customer.national_id_number},
        "vehicle": {"registration_number": "NEW-123"},
        "start_time": (start + timedelta(days=1)).isoformat(),
        "month_count": 1,
    }
    with patch(
        "parking_permits.admin_resolvers.update_or_create_customer",
        return_value=primary.customer,
    ):
        with pytest.raises(ParkingPermitValidationError):
            inspect.unwrap(resolve_create_resident_permit)(
                None, Mock(), payload, audit_msg=Mock()
            )
    secondary = ParkingPermitFactory(
        customer=primary.customer,
        primary_vehicle=False,
        address=primary.customer.primary_address,
        status="VALID",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=primary.end_time,
        month_count=1,
    )
    with pytest.raises(PermitCanNotBeExtendedError):
        inspect.unwrap(resolve_extend_parking_permit)(
            None, Mock(), secondary.pk, 1, audit_msg=Mock()
        )
    assert not secondary.permit_extension_requests.exists()


@pytest.mark.django_db
@freeze_time("2026-11-12T12:00:00+02:00")
def test_pending_extension_is_not_approved_after_primary_changes():
    from parking_permits.tests.factories.permit_extension_request import (
        ParkingPermitExtensionRequestFactory,
    )

    start = dt("2026-10-31T12:00")
    primary = ParkingPermitFactory(
        status="VALID",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=get_end_time(start, 3),
        month_count=3,
    )
    secondary = ParkingPermitFactory(
        customer=primary.customer,
        primary_vehicle=False,
        status="VALID",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=get_end_time(start, 1),
        month_count=1,
    )
    extension = ParkingPermitExtensionRequestFactory(permit=secondary, month_count=2)
    assert extension.get_end_time() == primary.end_time
    primary.end_time = secondary.end_time
    primary.save()
    with pytest.raises(PermitCanNotBeExtendedError):
        extension.approve()
    extension.refresh_from_db()
    secondary.refresh_from_db()
    assert extension.is_pending()
    assert secondary.month_count == 1


@pytest.mark.parametrize("months", [0, -1, 13])
def test_subscription_primary_does_not_remove_purchase_month_bounds(months):
    primary = permit("2026-11-12T12:00")
    primary.contract_type = "OPEN_ENDED"
    secondary = permit("2026-11-12T13:00", primary=False)
    secondary.month_count = months
    with pytest.raises(ParkingPermitValidationError):
        validate_secondary_permit(secondary, primary, purchase=True)


@pytest.mark.django_db
@freeze_time("2026-11-13T12:00:00+02:00")
@pytest.mark.parametrize("microsecond", [0, 123000, 999999])
def test_second_permit_can_buy_full_future_period_with_stored_end_precision(
    microsecond,
):
    start = dt("2026-11-14T00:00")
    primary = ParkingPermitFactory(
        status="VALID",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=get_end_time(start, 2).replace(microsecond=microsecond),
        month_count=2,
    )
    secondary = ParkingPermitFactory(
        customer=primary.customer,
        primary_vehicle=False,
        status="DRAFT",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=get_end_time(start, 1),
        month_count=1,
    )
    CustomerPermit(primary.customer_id).update(
        {"contract_type": "FIXED_PERIOD", "month_count": 2}, str(secondary.pk)
    )
    secondary.refresh_from_db()
    assert secondary.start_time == primary.start_time
    assert secondary.month_count == 2
    assert secondary.end_time == primary.end_time
    # Checkout uses the same full-duration validation as the draft update.
    secondary.validate_purchase()

    for start_time, months in ((start + timedelta(days=1), 2), (start, 3)):
        with pytest.raises(ParkingPermitValidationError):
            CustomerPermit(primary.customer_id).update(
                {
                    "start_time": start_time.isoformat(),
                    "contract_type": "FIXED_PERIOD",
                    "month_count": months,
                },
                str(secondary.pk),
            )
    secondary.refresh_from_db()
    assert secondary.end_time == primary.end_time


@pytest.mark.parametrize("end", ["2027-01-13T23:59:58", "2027-01-12T23:59:59"])
def test_matching_future_period_does_not_ignore_a_genuinely_earlier_end(end):
    from parking_permits.permit_rules import get_secondary_end_time

    primary = permit("2026-11-14T00:00", 2)
    primary.end_time = dt(end)
    secondary = permit("2026-11-14T00:00", 2, False)
    secondary.end_time = get_secondary_end_time(secondary.start_time, 2, primary)
    with pytest.raises(ParkingPermitValidationError):
        validate_secondary_permit(
            secondary, primary, purchase=True, now=dt("2026-11-13T12:00")
        )


@pytest.mark.django_db
@freeze_time("2026-11-13T12:00:00+02:00")
@pytest.mark.parametrize("day_offset", [0, 1])
@pytest.mark.parametrize("targeted", [False, True])
def test_reselecting_start_date_resets_second_permit_to_one_month(day_offset, targeted):
    start = dt("2026-11-14T00:00")
    primary = ParkingPermitFactory(
        status="VALID",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=get_end_time(start, 2).replace(microsecond=0),
        month_count=2,
    )
    secondary = ParkingPermitFactory(
        customer=primary.customer,
        primary_vehicle=False,
        status="DRAFT",
        contract_type="FIXED_PERIOD",
        start_time=start,
        end_time=get_end_time(start, 1),
        month_count=1,
    )
    service = CustomerPermit(primary.customer_id)
    service.update(
        {"month_count": 2, "contract_type": "FIXED_PERIOD"}, str(secondary.pk)
    )
    selected_start = start + timedelta(days=day_offset)
    service.update(
        {"start_type": "FROM", "start_time": selected_start.isoformat()},
        str(secondary.pk) if targeted else None,
    )
    secondary.refresh_from_db()
    primary.refresh_from_db()
    assert secondary.month_count == 1
    assert secondary.start_time == selected_start
    assert secondary.end_time == get_end_time(selected_start, 1)
    assert primary.month_count == 2
    assert primary.start_time == start
    if day_offset == 0:
        service.update(
            {"month_count": 2, "contract_type": "FIXED_PERIOD"}, str(secondary.pk)
        )
        secondary.refresh_from_db()
        assert secondary.month_count == 2
        assert secondary.end_time == primary.end_time
