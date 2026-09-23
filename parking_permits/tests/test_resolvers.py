import dataclasses
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.test import override_settings
from django.utils import timezone
from freezegun import freeze_time

from parking_permits.exceptions import DuplicatePermitError, PermitCanNotBeExtendedError
from parking_permits.models import Order, ParkingPermitExtensionRequest, Refund
from parking_permits.models.order import OrderStatus
from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus
from parking_permits.models.product import ProductType
from parking_permits.resolvers import (
    resolve_change_address,
    resolve_extend_parking_permit,
    resolve_get_extended_permit_price_list,
    resolve_update_permit_vehicle,
)
from parking_permits.tests.factories.address import AddressFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import OrderFactory, OrderItemFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import (
    VehicleFactory,
    VehiclePowerTypeFactory,
)
from parking_permits.tests.factories.zone import ParkingZoneFactory
from parking_permits.utils import get_end_time
from users.models import User


@dataclasses.dataclass
class Info:
    context: dict


@dataclasses.dataclass
class Auth:
    user: User


def _mock_talpa():
    return mock.patch(
        "parking_permits.talpa.order.TalpaOrderManager.send_to_talpa",
        return_value="https://talpa.fi",
    )


def _mock_jwt(user):
    return mock.patch(
        "helusers.oidc.RequestJWTAuthentication.authenticate",
        return_value=Auth(user=user),
    )


def _mock_price_change_list(price_change_list):
    return mock.patch(
        "parking_permits.models.ParkingPermit.get_price_change_list",
        return_value=price_change_list,
    )


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_update_permit_vehicle_high_to_low_emission(rf):
    """Should create a refund."""
    request = rf.post("/")
    customer = CustomerFactory()
    request.user = customer.user
    info = Info(context={"request": request})

    old_vehicle = VehicleFactory(power_type__identifier="04")
    new_vehicle = VehicleFactory(power_type__identifier="00")

    permit = ParkingPermitFactory(
        customer=customer,
        contract_type=ContractType.FIXED_PERIOD,
        status=ParkingPermitStatus.VALID,
        vehicle=old_vehicle,
    )

    order = OrderFactory(
        talpa_order_id="d4745a07-de99-33f8-94d6-64595f7a8bc6",
        customer=customer,
        status=OrderStatus.CONFIRMED,
    )
    order.permits.add(permit)
    order.save()

    price_change_list = [
        {
            "new_price": 50.00,
            "price_change_vat": 10.00,
            "price_change": -50.00,
            "price_change_vat_percent": 25.50,
            "month_count": 3,
        },
    ]

    with (
        _mock_price_change_list(price_change_list),
        _mock_jwt(request.user),
        _mock_talpa(),
    ):
        response = resolve_update_permit_vehicle(
            None, info, str(permit.pk), str(new_vehicle.pk)
        )

    assert response["checkout_url"] is None

    assert Order.objects.count() == 1
    assert Refund.objects.count() == 1

    #  3 months * 50 € = 150 €
    assert Refund.objects.first().amount == pytest.approx(
        Decimal(150.00), Decimal(0.01)
    )

    permit.refresh_from_db()
    assert permit.vehicle == new_vehicle
    assert permit.next_vehicle is None


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_update_permit_vehicle_low_to_high_emission(rf):
    """Should create an order."""
    request = rf.post("/")
    customer = CustomerFactory()
    request.user = customer.user
    info = Info(context={"request": request})

    new_vehicle = VehicleFactory(power_type__identifier="04")
    old_vehicle = VehicleFactory(power_type__identifier="00")

    permit = ParkingPermitFactory(
        customer=customer,
        contract_type=ContractType.FIXED_PERIOD,
        status=ParkingPermitStatus.VALID,
        vehicle=old_vehicle,
    )

    price_change_list = [
        {
            "new_price": 50.00,
            "price_change_vat": 10.00,
            "price_change": 50.00,
            "month_count": 3,
        },
    ]

    with (
        _mock_jwt(request.user),
        _mock_price_change_list(price_change_list),
        _mock_talpa(),
    ):
        response = resolve_update_permit_vehicle(
            None, info, str(permit.pk), str(new_vehicle.pk)
        )

    assert response["checkout_url"] == "https://talpa.fi"

    assert Order.objects.count() == 1
    assert Refund.objects.count() == 0

    permit.refresh_from_db()
    assert permit.vehicle == old_vehicle
    assert permit.next_vehicle == new_vehicle


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_update_open_ended_permit_vehicle_high_to_low_emission(rf):
    """Should not create a refund"""
    request = rf.post("/")
    customer = CustomerFactory()
    request.user = customer.user
    info = Info(context={"request": request})

    old_vehicle = VehicleFactory(power_type__identifier="04")
    new_vehicle = VehicleFactory(power_type__identifier="00")

    permit = ParkingPermitFactory(
        customer=customer,
        contract_type=ContractType.OPEN_ENDED,
        status=ParkingPermitStatus.VALID,
        vehicle=old_vehicle,
    )

    price_change_list = [
        {
            "new_price": 50.00,
            "price_change_vat": 10.00,
            "price_change": -50.00,
            "month_count": 0,
        },
    ]

    with (
        _mock_jwt(request.user),
        _mock_price_change_list(price_change_list),
        _mock_talpa(),
    ):
        response = resolve_update_permit_vehicle(
            None, info, str(permit.pk), str(new_vehicle.pk)
        )

    assert response["checkout_url"] is None

    assert Order.objects.count() == 0
    assert Refund.objects.count() == 0

    permit.refresh_from_db()
    assert permit.vehicle == new_vehicle
    assert permit.next_vehicle is None


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_update_permit_vehicle_high_to_high_emission(rf):
    """Should create no orders or refunds."""
    request = rf.post("/")
    customer = CustomerFactory()
    request.user = customer.user
    info = Info(context={"request": request})

    new_vehicle = VehicleFactory(power_type__identifier="00")
    old_vehicle = VehicleFactory(power_type__identifier="00")

    permit = ParkingPermitFactory(
        customer=customer,
        contract_type=ContractType.FIXED_PERIOD,
        status=ParkingPermitStatus.VALID,
        vehicle=old_vehicle,
    )

    price_change_list = [
        {
            "new_price": 50.00,
            "price_change_vat": 10.00,
            "price_change": 0.00,
            "month_count": 3,
        },
    ]

    with (
        _mock_jwt(request.user),
        _mock_price_change_list(price_change_list),
        _mock_talpa(),
    ):
        response = resolve_update_permit_vehicle(
            None, info, str(permit.pk), str(new_vehicle.pk)
        )

    assert response["checkout_url"] is None

    assert Order.objects.count() == 0
    assert Refund.objects.count() == 0

    permit.refresh_from_db()
    assert permit.vehicle == new_vehicle
    assert permit.next_vehicle is None


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_update_permit_vehicle_low_to_high_emission_raises_on_duplicate(rf):
    request = rf.post("/")
    customer = CustomerFactory()
    request.user = customer.user
    info = Info(context={"request": request})

    new_vehicle = VehicleFactory(power_type__identifier="04")
    ParkingPermitFactory(
        customer=customer,
        contract_type=ContractType.FIXED_PERIOD,
        status=ParkingPermitStatus.VALID,
        vehicle=new_vehicle,
    )

    old_vehicle = VehicleFactory(power_type__identifier="00")
    permit_to_update = ParkingPermitFactory(
        customer=customer,
        contract_type=ContractType.FIXED_PERIOD,
        status=ParkingPermitStatus.VALID,
        vehicle=old_vehicle,
    )

    price_change_list = [
        {
            "new_price": 50.00,
            "price_change_vat": 10.00,
            "price_change": 50.00,
            "month_count": 3,
        },
    ]

    with (
        _mock_jwt(request.user),
        _mock_price_change_list(price_change_list),
        _mock_talpa(),
        pytest.raises(DuplicatePermitError),
    ):
        resolve_update_permit_vehicle(
            None, info, str(permit_to_update.pk), str(new_vehicle.pk)
        )


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_resolve_change_address_change_to_parking_zone_with_higher_price(rf):
    request = rf.post("/")
    customer = CustomerFactory()
    order = OrderFactory(customer=customer)

    permit = ParkingPermitFactory(
        customer=customer,
        contract_type=ContractType.FIXED_PERIOD,
        status=ParkingPermitStatus.VALID,
    )
    order.permits.add(permit)

    address = AddressFactory()
    customer.primary_address = address
    customer.save()

    request.user = customer.user

    info = Info(context={"request": request})
    price_change_list = [
        {
            "new_price": 100.00,
            "price_change_vat": 10.00,
            "price_change": 50.00,
            "month_count": 3,
        },
    ]

    with (
        _mock_jwt(request.user),
        _mock_price_change_list(price_change_list),
        _mock_talpa(),
    ):
        response = resolve_change_address(None, info, str(address.pk))

    assert response["success"]
    assert Order.objects.count() == 2
    new_order = Order.objects.exclude(pk=order.pk).first()
    assert new_order.status == OrderStatus.DRAFT


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_resolve_change_address_change_to_parking_zone_same_price(rf):
    request = rf.post("/")
    customer = CustomerFactory()
    order = OrderFactory(customer=customer)

    permit = ParkingPermitFactory(
        customer=customer,
        contract_type=ContractType.FIXED_PERIOD,
        status=ParkingPermitStatus.VALID,
    )
    order.permits.add(permit)

    address = AddressFactory()
    customer.primary_address = address
    customer.save()

    request.user = customer.user

    info = Info(context={"request": request})

    with (
        _mock_jwt(request.user),
        _mock_price_change_list([]),
        _mock_talpa(),
    ):
        response = resolve_change_address(None, info, str(address.pk))

    assert response["success"]
    assert Order.objects.count() == 1
    assert Refund.objects.count() == 0


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_resolve_change_address_change_to_parking_zone_with_refund(rf):
    request = rf.post("/")
    customer = CustomerFactory()
    order = OrderFactory(customer=customer)

    permit = ParkingPermitFactory(
        customer=customer,
        contract_type=ContractType.FIXED_PERIOD,
        status=ParkingPermitStatus.VALID,
    )
    order.permits.add(permit)

    address = AddressFactory()
    customer.primary_address = address
    customer.save()

    request.user = customer.user

    info = Info(context={"request": request})
    price_change_list = [
        {
            "new_price": Decimal("100.00"),
            "price_change_vat": Decimal("25.50"),
            "price_change": Decimal("-50.00"),
            "month_count": 3,
        },
    ]

    with (
        _mock_jwt(request.user),
        _mock_price_change_list(price_change_list),
        _mock_talpa(),
    ):
        response = resolve_change_address(None, info, str(address.pk))

    assert response["success"]
    assert Order.objects.count() == 1
    assert Refund.objects.count() == 1


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_resolve_change_address_no_change_to_parking_zone(rf):
    request = rf.post("/")
    customer = CustomerFactory()
    permit = ParkingPermitFactory(customer=customer, status=ParkingPermitStatus.VALID)

    address = AddressFactory(_zone=permit.parking_zone)
    customer.primary_address = address
    customer.save()

    request.user = customer.user

    info = Info(context={"request": request})

    with _mock_jwt(request.user):
        response = resolve_change_address(None, info, str(address.pk))

    assert response["success"]
    assert Order.objects.count() == 0


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_resolve_get_extended_permit_price_list(rf):
    request = rf.post("/")
    customer = CustomerFactory()

    now = timezone.now()
    permit = ParkingPermitFactory(
        customer=customer,
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.FIXED_PERIOD,
        start_time=now,
        end_time=now + timedelta(days=10),
    )

    ProductFactory(
        zone=permit.parking_zone,
        type=ProductType.RESIDENT,
        start_date=(now - timedelta(days=360)).date(),
        end_date=(now + timedelta(days=360)).date(),
    )
    request.user = customer.user

    info = Info(context={"request": request})

    with _mock_jwt(request.user):
        response = resolve_get_extended_permit_price_list(None, info, str(permit.pk), 3)

    assert len(list(response)) == 1


@pytest.mark.django_db()
@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True, PERMIT_EXTENSIONS_ENABLED=True)
def test_resolve_extend_parking_permit_ok(rf):
    request = rf.post("/")
    customer = CustomerFactory()

    now = timezone.now()
    permit = ParkingPermitFactory(
        customer=customer,
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.FIXED_PERIOD,
        start_time=now,
        end_time=now + timedelta(days=10),
    )
    permit.address = permit.customer.primary_address
    permit.save()

    ProductFactory(
        zone=permit.parking_zone,
        type=ProductType.RESIDENT,
        start_date=(now - timedelta(days=360)).date(),
        end_date=(now + timedelta(days=360)).date(),
    )
    request.user = customer.user

    info = Info(context={"request": request})

    with (
        _mock_jwt(request.user),
        _mock_talpa(),
    ):
        response = resolve_extend_parking_permit(None, info, str(permit.pk), 3)

    assert response["checkout_url"] == "https://talpa.fi"

    assert ParkingPermitExtensionRequest.objects.count() == 1

    ext_request = ParkingPermitExtensionRequest.objects.first()
    assert ext_request.month_count == 3
    assert ext_request.permit == permit


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_resolve_extend_parking_permit_invalid(rf):
    request = rf.post("/")
    customer = CustomerFactory()

    now = timezone.now()
    permit = ParkingPermitFactory(
        customer=customer,
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.FIXED_PERIOD,
        start_time=now,
        end_time=now + timedelta(days=30),
    )

    request.user = customer.user

    info = Info(context={"request": request})

    with _mock_jwt(request.user):
        with pytest.raises(PermitCanNotBeExtendedError):
            resolve_extend_parking_permit(None, info, str(permit.pk), 3)

    assert ParkingPermitExtensionRequest.objects.count() == 0


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_update_permit_vehicle_electric_to_non_electric_creates_payment_with_real_price_change(
    rf,
):
    """Uses real product/vehicle data (not a mocked price_change_list) to
    verify that switching from an electric (discounted) to a non-electric
    (full price) vehicle correctly computes a price increase and creates
    a new order rather than a refund."""
    request = rf.post("/")
    customer = CustomerFactory()
    request.user = customer.user
    info = Info(context={"request": request})

    zone = ParkingZoneFactory(name="A")
    start_time = timezone.make_aware(datetime(2021, 1, 1))
    end_time = get_end_time(start_time, 12)
    ProductFactory(
        zone=zone,
        type=ProductType.RESIDENT,
        start_date=start_time.date(),
        end_date=end_time.date(),
        unit_price=Decimal("20"),
        low_emission_discount=Decimal("0.5"),
    )

    old_vehicle = VehicleFactory(power_type=VehiclePowerTypeFactory(identifier="04"))
    new_vehicle = VehicleFactory(power_type=VehiclePowerTypeFactory(identifier="00"))

    permit = ParkingPermitFactory(
        customer=customer,
        parking_zone=zone,
        contract_type=ContractType.FIXED_PERIOD,
        status=ParkingPermitStatus.VALID,
        vehicle=old_vehicle,
        start_time=start_time,
        end_time=end_time,
        month_count=12,
    )

    # create_renewal_order() looks up permit.latest_order (via
    # get_unused_order_items) to prorate the new order, so an existing
    # confirmed order/order item covering the permit period is required.
    # Prices of the order reflect the pre-change, electric-discounted prices.
    order = OrderFactory(customer=customer, status=OrderStatus.CONFIRMED)
    OrderItemFactory(
        order=order,
        permit=permit,
        unit_price=Decimal("10"),
        payment_unit_price=Decimal("10"),
        vat=Decimal("0.255"),
        quantity=12,
        start_time=start_time,
        end_time=end_time,
    )
    order.permits.add(permit)

    # months_used/next_period_start_time depend on "now", so only the
    # actual price computation + resolver call needs to be frozen
    with (
        freeze_time("2021-04-15"),
        _mock_jwt(request.user),
        _mock_talpa(),
    ):
        response = resolve_update_permit_vehicle(
            None, info, str(permit.pk), str(new_vehicle.pk)
        )

    assert response["checkout_url"] == "https://talpa.fi"
    assert Order.objects.count() == 2
    assert Refund.objects.count() == 0

    permit.refresh_from_db()
    assert permit.vehicle == old_vehicle
    assert permit.next_vehicle == new_vehicle


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
def test_update_permit_vehicle_non_electric_to_electric_creates_refund_with_real_price_change(
    rf,
):
    """Uses real product/vehicle data to verify that switching from a
    non-electric (full price) to an electric (discounted) vehicle
    correctly computes a price decrease and creates a refund for the
    exact price difference."""
    request = rf.post("/")
    customer = CustomerFactory()
    request.user = customer.user
    info = Info(context={"request": request})

    zone = ParkingZoneFactory(name="A")
    start_time = timezone.make_aware(datetime(2021, 1, 1))
    end_time = get_end_time(start_time, 12)
    ProductFactory(
        zone=zone,
        type=ProductType.RESIDENT,
        start_date=start_time.date(),
        end_date=end_time.date(),
        unit_price=Decimal("20"),
        low_emission_discount=Decimal("0.5"),
    )

    old_vehicle = VehicleFactory(power_type=VehiclePowerTypeFactory(identifier="00"))
    new_vehicle = VehicleFactory(power_type=VehiclePowerTypeFactory(identifier="04"))

    permit = ParkingPermitFactory(
        customer=customer,
        parking_zone=zone,
        contract_type=ContractType.FIXED_PERIOD,
        status=ParkingPermitStatus.VALID,
        vehicle=old_vehicle,
        start_time=start_time,
        end_time=end_time,
        month_count=12,
    )

    order = OrderFactory(
        talpa_order_id="d4745a07-de99-33f8-94d6-64595f7a8bc6",
        customer=customer,
        status=OrderStatus.CONFIRMED,
    )
    order.permits.add(permit)
    order.save()

    # months_used/next_period_start_time depend on "now", so only the
    # actual price computation + resolver call needs to be frozen
    with (
        freeze_time("2021-04-15"),
        _mock_jwt(request.user),
        _mock_talpa(),
    ):
        response = resolve_update_permit_vehicle(
            None, info, str(permit.pk), str(new_vehicle.pk)
        )

    assert response["checkout_url"] is None
    assert Order.objects.count() == 1
    assert Refund.objects.count() == 1
    # permit started 2021-01-01, frozen "now" is 2021-04-15, so the next
    # (unpaid) period starts 2021-05-01, leaving 8 remaining months
    # (May-Dec) at 20 € -> 10 € (50% discount) = -10 €/month: 8 * 10 = 80 €
    assert Refund.objects.first().amount == pytest.approx(
        Decimal("80.00"), Decimal("0.01")
    )

    permit.refresh_from_db()
    assert permit.vehicle == new_vehicle
    assert permit.next_vehicle is None
