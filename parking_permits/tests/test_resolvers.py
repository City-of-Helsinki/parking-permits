import dataclasses
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from parking_permits.exceptions import (
    DuplicatePermitError,
    ObjectNotFoundError,
    OrderCreationFailedError,
    PermitCanNotBeExtendedError,
    PermitRenewalPeriodError,
    RefundReconciliationRequiredError,
)
from parking_permits.models import Order, ParkingPermitExtensionRequest, Refund
from parking_permits.models.order import OrderStatus, OrderType
from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus
from parking_permits.models.product import ProductType
from parking_permits.resolver_utils import create_refund
from parking_permits.resolvers import (
    resolve_change_address,
    resolve_end_permit,
    resolve_extend_parking_permit,
    resolve_get_extended_permit_price_list,
    resolve_get_update_address_price_changes,
    resolve_get_vehicle_price_changes,
    resolve_update_permit_vehicle,
)
from parking_permits.talpa.order import TalpaOrderManager
from parking_permits.tests.factories.address import AddressFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import OrderFactory, OrderItemFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import VehicleFactory
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
    def quote(permit, **kwargs):
        if not permit.is_fixed_period or not any(
            line["price_change"] for line in price_change_list
        ):
            return price_change_list
        order = permit.latest_order or OrderFactory(customer=permit.customer)
        order.permits.add(permit)
        source = OrderItemFactory(order=order, permit=permit)
        return [
            dict(
                {
                    "tariff_prices": (Decimal("100"), Decimal("50")),
                    "tariff_product": source.product,
                    "source_item": source,
                    "funding_order": order,
                    "price_change_vat_percent": Decimal("25.5"),
                    "start_date": date(2021, 1, 1),
                    "end_date": date(2021, 3, 31),
                },
                **line,
            )
            for line in price_change_list
        ]

    return mock.patch(
        "parking_permits.models.ParkingPermit.get_price_change_list",
        autospec=True,
        side_effect=quote,
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
            "price_change": Decimal("-50.00"),
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
    assert response["refund_created"] is True

    assert Order.objects.filter(type=OrderType.PRICE_ADJUSTED).count() == 1
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
    assert response["refund_created"] is False

    assert Order.objects.filter(type=OrderType.VEHICLE_CHANGED).count() == 1
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
            "price_change": Decimal("-50.00"),
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
    assert response["refund_created"] is False

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
    assert response["refund_created"] is False

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
    assert Order.objects.filter(type=OrderType.PRICE_ADJUSTED).count() == 1
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


@pytest.fixture
def prepaid_permit(rf):
    def purchase(low_emission=False, months=12):
        customer = CustomerFactory()
        zone = ParkingZoneFactory()
        start = timezone.make_aware(datetime(2021, 1, 1))
        product = ProductFactory(
            zone=zone,
            type=ProductType.RESIDENT,
            start_date=date(2021, 1, 1),
            end_date=date(2021, 12, 31),
            unit_price=Decimal("60"),
            low_emission_discount=Decimal("0.5"),
        )
        vehicle = VehicleFactory(power_type__identifier="04" if low_emission else "00")
        permit = ParkingPermitFactory(
            customer=customer,
            parking_zone=zone,
            vehicle=vehicle,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.VALID,
            start_time=start,
            end_time=get_end_time(start, months),
            month_count=months,
        )
        Order.objects.create_for_permits([permit], status=OrderStatus.CONFIRMED)
        product.end_date = date(2021, 9, 30)
        product.save()
        ProductFactory(
            zone=zone,
            type=ProductType.RESIDENT,
            start_date=date(2021, 10, 1),
            end_date=date(2021, 12, 31),
            unit_price=Decimal("70"),
            low_emission_discount=Decimal("0.5"),
        )
        request = rf.post("/")
        request.user = customer.user
        return permit, Info(context={"request": request})

    return purchase


def quote_total(lines):
    return sum(line["price_change"] * line["month_count"] for line in lines)


@pytest.mark.django_db
@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@freeze_time("2021-04-15")
@pytest.mark.parametrize("low_emission, paid_rate", [(False, 60), (True, 30)])
def test_ending_refunds_unused_months_at_purchase_price(
    prepaid_permit, client, low_emission, paid_rate
):
    permit, _ = prepaid_permit(low_emission=low_emission)
    url = reverse("parking_permits:graphql")
    with _mock_jwt(permit.customer.user):
        preview = client.post(
            url,
            {
                "query": """{ getPermits {
                totalRefundAmount
                endingRefundLines { priceChange monthCount startDate endDate }
            } }"""
            },
            content_type="application/json",
        ).json()
        assert preview == {
            "data": {
                "getPermits": [
                    {
                        "totalRefundAmount": 8 * paid_rate,
                        "endingRefundLines": [
                            {
                                "priceChange": paid_rate,
                                "monthCount": 8,
                                "startDate": "2021-05-01",
                                "endDate": "2021-12-31",
                            }
                        ],
                    }
                ]
            }
        }
        result = client.post(
            url,
            {
                "query": """mutation End($ids: [String]!) {
                    endParkingPermit(permitIds: $ids, endType: IMMEDIATELY, iban: "FI2112345600000785")
                }""",
                "variables": {"ids": [str(permit.pk)]},
            },
            content_type="application/json",
        ).json()
    assert result == {"data": {"endParkingPermit": True}}
    assert Refund.objects.get().amount == paid_rate * 8


@pytest.mark.django_db
@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@freeze_time("2021-04-15")
@pytest.mark.parametrize("initially_electric", [True, False])
def test_vehicle_preview_matches_prepaid_adjustment(prepaid_permit, initially_electric):
    permit, info = prepaid_permit(low_emission=initially_electric)
    old_vehicle = permit.vehicle
    new_vehicle = VehicleFactory(
        power_type__identifier="00" if initially_electric else "04"
    )
    with _mock_jwt(permit.customer.user), _mock_talpa() as checkout:
        quote = resolve_get_vehicle_price_changes(
            None, info, permit.pk, new_vehicle.is_low_emission
        )
        expected = Decimal("240") if initially_electric else Decimal("-240")
        assert quote_total(quote) == expected
        resolve_update_permit_vehicle(None, info, permit.pk, new_vehicle.pk)
        if initially_electric:
            order = checkout.call_args.args[0]
            assert order.total_payment_price == expected
            assert TalpaOrderManager.create_order_data(order)["priceTotal"] == "240.00"
            assert order.status == OrderStatus.CONFIRMED
            assert not Refund.objects.exists()
        else:
            checkout.assert_not_called()
            assert Refund.objects.get().amount == -expected
            permit.refresh_from_db()
            assert permit.total_refund_amount == -expected
            # No payment is made between the refund and switching back.
            quote = resolve_get_vehicle_price_changes(
                None, info, permit.pk, old_vehicle.is_low_emission
            )
            resolve_update_permit_vehicle(None, info, permit.pk, old_vehicle.pk)
            assert (
                checkout.call_args.args[0].total_payment_price
                == quote_total(quote)
                == -expected
            )


@pytest.mark.django_db
@freeze_time("2021-04-15")
@pytest.mark.parametrize("legacy", [False, True])
def test_vehicle_quote_keeps_purchased_tariff(prepaid_permit, legacy):
    permit, info = prepaid_permit()
    item = permit.order_items.get()
    if legacy:
        # Pre-migration purchase with a later, separately priced product.
        permit.order_items.update(regular_unit_price=None, discounted_unit_price=None)
    else:
        # Even an in-place edit cannot alter a snapshotted purchase.
        product = item.product
        product.unit_price = Decimal("100")
        product.low_emission_discount = Decimal("0.25")
        product.save()
    with _mock_jwt(permit.customer.user):
        assert (
            quote_total(resolve_get_vehicle_price_changes(None, info, permit.pk, True))
            == -240
        )


@pytest.mark.django_db
@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@freeze_time("2021-04-15")
@pytest.mark.parametrize("destination_rate", [80, 40])
def test_address_preview_prices_destination_zone(prepaid_permit, destination_rate):
    permit, info = prepaid_permit()
    destination = ParkingZoneFactory()
    ProductFactory(
        zone=destination,
        type=ProductType.RESIDENT,
        unit_price=Decimal(destination_rate),
    )
    address = AddressFactory(_zone=destination)
    permit.customer.primary_address = address
    permit.customer.save()
    with _mock_jwt(permit.customer.user), _mock_talpa() as checkout:
        preview = resolve_get_update_address_price_changes(None, info, str(address.pk))
        resolve_change_address(None, info, str(address.pk))
    total = quote_total(preview[0]["price_changes"])
    assert total == (destination_rate - 60) * 8
    if total > 0:
        order = checkout.call_args.args[0]
        assert order.total_payment_price == total
        assert order.order_items.get().product.zone == destination
    else:
        checkout.assert_not_called()
        assert Refund.objects.get().amount == -total
        # The next vehicle change uses the applied destination tariff.
        with _mock_jwt(permit.customer.user):
            assert (
                quote_total(
                    resolve_get_vehicle_price_changes(None, info, permit.pk, True)
                )
                == -160
            )


@pytest.mark.django_db
@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@freeze_time("2021-04-15")
def test_vehicle_change_includes_purchase_and_confirmed_extension(prepaid_permit):
    permit, info = prepaid_permit(months=9)
    extension = Order.objects.create_for_extended_permit(permit, 3)
    request = ParkingPermitExtensionRequest.objects.create(
        permit=permit, order=extension, month_count=3
    )
    request.approve()
    electric = VehicleFactory(power_type__identifier="04")
    with _mock_jwt(permit.customer.user), _mock_talpa() as checkout:
        quote = resolve_get_vehicle_price_changes(None, info, permit.pk, True)
        resolve_update_permit_vehicle(None, info, permit.pk, electric.pk)
    checkout.assert_not_called()
    assert [(line["month_count"], line["previous_price"]) for line in quote] == [
        (5, 60),
        (3, 70),
    ]
    assert quote_total(quote) == -255
    assert sorted(Refund.objects.values_list("amount", flat=True)) == [105, 150]
    assert extension.refunds.get().amount == 105
    # Ending refunds the balance of both purchases after the vehicle discount.
    assert quote_total(permit.ending_refund_lines) == 255


@pytest.mark.django_db
@freeze_time("2021-04-15")
def test_vehicle_preview_does_not_disclose_other_customers_permit(prepaid_permit):
    permit, _ = prepaid_permit()
    other, info = prepaid_permit()
    with (
        _mock_jwt(other.customer.user),
        pytest.raises(ObjectNotFoundError, match="Permit not found"),
    ):
        resolve_get_vehicle_price_changes(None, info, permit.pk, True)


@pytest.mark.django_db
@freeze_time("2021-04-15")
def test_checkout_uses_order_that_put_permit_in_payment(prepaid_permit):
    permit, _ = prepaid_permit(months=9)
    extension = Order.objects.create_for_extended_permit(
        permit, 3, status=OrderStatus.DRAFT
    )
    extension.talpa_checkout_url = "https://example.org/extension"
    extension.save()
    permit.permit_extension_requests.create(order=extension, month_count=3)
    change = OrderFactory(customer=permit.customer, type=OrderType.VEHICLE_CHANGED)
    change.permits.add(permit)
    assert permit.checkout_url == extension.talpa_checkout_url
    permit.status = ParkingPermitStatus.PAYMENT_IN_PROGRESS
    assert permit.checkout_url == change.talpa_checkout_url


@pytest.mark.django_db
@freeze_time("2021-04-15")
@pytest.mark.parametrize("known_pair", [False, True])
def test_legacy_tariff_after_in_place_product_edit(prepaid_permit, known_pair):
    permit, _ = prepaid_permit()
    purchase = permit.order_items.get()
    purchase.regular_unit_price = purchase.discounted_unit_price = None
    purchase.save()
    purchase.product.unit_price = Decimal("90")
    purchase.product.save()
    if known_pair:
        order = OrderFactory(
            customer=permit.customer,
            type=OrderType.VEHICLE_CHANGED,
            status=OrderStatus.CONFIRMED,
        )
        OrderItemFactory(
            order=order,
            product=purchase.product,
            permit=permit,
            unit_price=30,
            payment_unit_price=-30,
            start_time=purchase.start_time,
            end_time=purchase.end_time,
        )
    assert purchase.tariff_prices(False) == (60, 30 if known_pair else 60)
    if not known_pair:
        assert (
            quote_total(permit.fixed_period_price_changes(permit.parking_zone, True))
            == 0
        )


@pytest.mark.django_db
@freeze_time("2021-04-15")
def test_overlap_respects_billed_quantity_and_rejects_ambiguous_rows(prepaid_permit):
    permit, _ = prepaid_permit()
    purchase = permit.order_items.get()
    purchase.quantity = 6
    purchase.save()
    second = OrderItemFactory(
        order=purchase.order,
        permit=permit,
        product=purchase.product,
        start_time=timezone.make_aware(datetime(2021, 7, 1)),
        end_time=permit.end_time,
        quantity=6,
        regular_unit_price=70,
        discounted_unit_price=35,
        unit_price=70,
        payment_unit_price=70,
    )
    lines = permit.fixed_period_price_changes(permit.parking_zone, True)
    assert [(line["source_item"], line["month_count"]) for line in lines] == [
        (purchase, 2),
        (second, 6),
    ]
    purchase.quantity = 7
    purchase.end_time = second.start_time
    purchase.save()
    assert (
        quote_total(permit.fixed_period_price_changes(permit.parking_zone, True))
        == -270
    )
    purchase.quantity = 12
    purchase.end_time = permit.end_time
    purchase.save()
    with pytest.raises(OrderCreationFailedError, match="Ambiguous paid coverage"):
        permit.fixed_period_price_changes(permit.parking_zone, True)


@pytest.mark.django_db
@freeze_time("2021-04-15")
def test_ending_deducts_only_unused_portion_of_legacy_vehicle_credit(prepaid_permit):
    permit, _ = prepaid_permit()
    order = permit.latest_order
    permit.order_items.update(regular_unit_price=None, discounted_unit_price=None)
    create_refund(
        permit.customer.user,
        [permit],
        [order],
        Decimal("240"),
        "",
        vat=order.vat,
        description="Refund for updating permits, customer switched vehicle to: EV",
    )
    assert permit.total_refund_amount == quote_total(permit.ending_refund_lines) == 240
    with freeze_time("2021-06-15"):
        assert (
            permit.total_refund_amount == quote_total(permit.ending_refund_lines) == 180
        )


@pytest.mark.django_db
@freeze_time("2021-04-15")
def test_shared_legacy_credit_blocks_ending_until_reconciled(prepaid_permit):
    permit, info = prepaid_permit()
    other = ParkingPermitFactory(customer=permit.customer, primary_vehicle=False)
    purchase = permit.latest_order
    refund = create_refund(
        permit.customer.user,
        [permit, other],
        [purchase],
        Decimal("240"),
        "",
        vat=purchase.vat,
        description="Refund for updating permits zone (customer switch address)",
    )
    assert permit.total_refund_amount is None
    assert permit.ending_refund_lines == []
    with (
        _mock_jwt(permit.customer.user),
        pytest.raises(RefundReconciliationRequiredError, match=str(refund.pk)),
    ):
        resolve_end_permit(None, info, [str(permit.pk)], "IMMEDIATELY", "")
    permit.refresh_from_db()
    assert permit.is_valid
    assert Refund.objects.count() == 1

    changes = permit.fixed_period_price_changes(permit.parking_zone, True)
    adjustment = Order.objects.create_renewal_order(
        permit.customer,
        status=OrderStatus.CONFIRMED,
        order_type=OrderType.PRICE_ADJUSTED,
        price_changes={permit.pk: changes},
    )
    refund.orders.add(adjustment)
    assert permit.total_refund_amount == quote_total(permit.ending_refund_lines) == 240


@pytest.mark.django_db
@freeze_time("2021-04-15")
@pytest.mark.parametrize("refund_date", ["2021-04-15", "2021-05-01T00:00:00+03:00"])
def test_legacy_vehicle_credits_with_several_rates_need_review_after_a_month(
    prepaid_permit, refund_date
):
    permit, info = prepaid_permit()
    order = permit.latest_order
    with freeze_time(refund_date):
        # Both amounts divide evenly across the eight months, so only the
        # sibling check can rule out prorating each row as a uniform credit.
        for amount in (Decimal("120"), Decimal("136")):
            create_refund(
                permit.customer.user,
                [permit],
                [order],
                amount,
                "",
                vat=order.vat,
                description="Refund for updating permits, customer switched vehicle to: EV",
            )
        assert permit.next_period_start_time == date(2021, 5, 1)
        assert permit.total_refund_amount == 224
    with freeze_time("2021-05-15"):
        assert permit.total_refund_amount is None
        assert permit.ending_refund_lines == []
        with (
            _mock_jwt(permit.customer.user),
            pytest.raises(RefundReconciliationRequiredError),
        ):
            resolve_end_permit(None, info, [str(permit.pk)], "IMMEDIATELY", "")
        assert Refund.objects.count() == 2


RENEWAL_NOW = timezone.make_aware(datetime(2024, 4, 29, 12, 0))
RENEWAL_PERIOD_END = timezone.make_aware(datetime(2024, 4, 30, 23, 59, 59))
NORMAL_PERIOD_END = timezone.make_aware(datetime(2024, 5, 14, 23, 59, 59))


def _open_ended_permit(customer, end_time, **kwargs):
    return ParkingPermitFactory(
        customer=customer,
        contract_type=ContractType.OPEN_ENDED,
        status=ParkingPermitStatus.VALID,
        start_time=end_time - timedelta(days=30),
        end_time=end_time,
        month_count=1,
        **kwargs,
    )


def _customer_info(rf, customer):
    request = rf.post("/")
    request.user = customer.user
    return Info(context={"request": request})


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
@freeze_time(RENEWAL_NOW)
def test_vehicle_change_blocked_for_permit_in_renewal_period(rf):
    customer = CustomerFactory()
    info = _customer_info(rf, customer)
    old_vehicle = VehicleFactory()
    permit = _open_ended_permit(customer, RENEWAL_PERIOD_END, vehicle=old_vehicle)
    new_vehicle = VehicleFactory()

    with _mock_jwt(info.context["request"].user):
        with pytest.raises(PermitRenewalPeriodError):
            resolve_get_vehicle_price_changes(None, info, permit.pk, True)
        with pytest.raises(PermitRenewalPeriodError):
            resolve_update_permit_vehicle(
                None, info, str(permit.pk), str(new_vehicle.pk)
            )

    permit.refresh_from_db()
    assert permit.vehicle == old_vehicle


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
@freeze_time(RENEWAL_NOW)
def test_vehicle_change_allowed_when_only_other_permit_in_renewal_period(rf):
    customer = CustomerFactory()
    info = _customer_info(rf, customer)
    _open_ended_permit(customer, RENEWAL_PERIOD_END)
    permit = _open_ended_permit(customer, NORMAL_PERIOD_END)
    new_vehicle = VehicleFactory(power_type__identifier="04")
    no_price_change = [
        {
            "new_price": 50.00,
            "price_change_vat": 0,
            "price_change": Decimal("0"),
            "month_count": 0,
        },
    ]

    with (
        _mock_jwt(info.context["request"].user),
        _mock_price_change_list(no_price_change),
        _mock_talpa(),
    ):
        resolve_update_permit_vehicle(None, info, str(permit.pk), str(new_vehicle.pk))

    permit.refresh_from_db()
    assert permit.vehicle == new_vehicle


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
@pytest.mark.django_db()
@freeze_time(RENEWAL_NOW)
def test_address_change_blocked_when_any_permit_in_renewal_period(rf):
    customer = CustomerFactory()
    info = _customer_info(rf, customer)
    zone = ParkingZoneFactory()
    _open_ended_permit(customer, NORMAL_PERIOD_END, parking_zone=zone)
    _open_ended_permit(customer, RENEWAL_PERIOD_END, parking_zone=zone)
    address = AddressFactory()
    customer.primary_address = address
    customer.save()

    with _mock_jwt(info.context["request"].user):
        with pytest.raises(PermitRenewalPeriodError):
            resolve_get_update_address_price_changes(None, info, str(address.pk))
        with pytest.raises(PermitRenewalPeriodError):
            resolve_change_address(None, info, str(address.pk))

    assert Order.objects.count() == 0
