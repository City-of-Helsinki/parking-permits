import dataclasses
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.test import override_settings
from django.utils import timezone

from parking_permits.exceptions import PermitCanNotBeExtended
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
from parking_permits.tests.factories.order import OrderFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import VehicleFactory
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
        with pytest.raises(PermitCanNotBeExtended):
            resolve_extend_parking_permit(None, info, str(permit.pk), 3)

    assert ParkingPermitExtensionRequest.objects.count() == 0
