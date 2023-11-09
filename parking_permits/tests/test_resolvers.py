import dataclasses
import decimal
import unittest

import pytest

from parking_permits.models import Order
from parking_permits.models.order import OrderStatus
from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus
from parking_permits.resolvers import resolve_change_address
from parking_permits.tests.factories.address import AddressFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import OrderFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from users.models import User


@dataclasses.dataclass
class Info:
    context: dict


@dataclasses.dataclass
class Auth:
    user: User


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
        unittest.mock.patch(
            "helusers.oidc.RequestJWTAuthentication.authenticate",
            return_value=Auth(user=request.user),
        ),
        unittest.mock.patch(
            "parking_permits.models.ParkingPermit.get_price_change_list",
            return_value=price_change_list,
        ),
        unittest.mock.patch(
            "parking_permits.talpa.order.TalpaOrderManager.send_to_talpa",
            return_value="https://talpa.fi",
        ),
    ):
        response = resolve_change_address(None, info, str(address.pk))

    assert response["success"]
    assert Order.objects.count() == 2
    new_order = Order.objects.exclude(pk=order.pk).first()
    assert new_order.status == OrderStatus.DRAFT


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
        unittest.mock.patch(
            "helusers.oidc.RequestJWTAuthentication.authenticate",
            return_value=Auth(user=request.user),
        ),
        unittest.mock.patch(
            "parking_permits.models.ParkingPermit.get_price_change_list",
            return_value=[],
        ),
        unittest.mock.patch(
            "parking_permits.talpa.order.TalpaOrderManager.send_to_talpa",
            return_value="https://talpa.fi",
        ),
    ):
        response = resolve_change_address(None, info, str(address.pk))

    assert response["success"]
    assert Order.objects.count() == 2

    new_order = Order.objects.exclude(pk=order.pk).first()
    assert new_order.status == OrderStatus.CONFIRMED


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
            "new_price": decimal.Decimal("100.00"),
            "price_change_vat": decimal.Decimal("10.00"),
            "price_change": decimal.Decimal("-50.00"),
            "month_count": 3,
        },
    ]

    with (
        unittest.mock.patch(
            "helusers.oidc.RequestJWTAuthentication.authenticate",
            return_value=Auth(user=request.user),
        ),
        unittest.mock.patch(
            "parking_permits.models.ParkingPermit.get_price_change_list",
            return_value=price_change_list,
        ),
        unittest.mock.patch(
            "parking_permits.talpa.order.TalpaOrderManager.send_to_talpa",
            return_value="https://talpa.fi",
        ),
    ):
        response = resolve_change_address(None, info, str(address.pk))

    assert response["success"]
    assert Order.objects.count() == 2

    new_order = Order.objects.exclude(pk=order.pk).first()
    assert new_order.status == OrderStatus.CONFIRMED


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

    with unittest.mock.patch(
        "helusers.oidc.RequestJWTAuthentication.authenticate",
        return_value=Auth(user=request.user),
    ):
        response = resolve_change_address(None, info, str(address.pk))

    assert response["success"]
    assert Order.objects.count() == 0
