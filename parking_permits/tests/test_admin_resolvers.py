import dataclasses
import unittest
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest import mock

import pytest
from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import Group
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from parking_permits import admin_resolvers
from parking_permits.admin_resolvers import (
    add_temporary_vehicle,
    resolve_create_product,
    resolve_create_resident_permit,
    resolve_extend_parking_permit,
    resolve_get_extended_permit_price_list,
    resolve_permit_price_change_list,
    resolve_update_resident_permit,
    resolve_vehicle,
    update_or_create_customer,
    update_or_create_vehicle,
)
from parking_permits.cron import automatic_expiration_of_permits
from parking_permits.exceptions import (
    AddressError,
    CreatePermitError,
    EndPermitError,
    InvalidEmailError,
    ObjectNotFoundError,
    PermitCanNotBeExtendedError,
    TraficomFetchVehicleError,
    UpdatePermitError,
)
from parking_permits.models import (
    Customer,
    Order,
    ParkingPermitExtensionRequest,
    Product,
    Refund,
)
from parking_permits.models.order import OrderStatus
from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus
from parking_permits.models.product import Accounting, ProductType
from parking_permits.tests.factories.address import AddressFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import OrderFactory, OrderItemFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import (
    TemporaryVehicleFactory,
    VehicleFactory,
    VehiclePowerTypeFactory,
)
from parking_permits.tests.factories.zone import ParkingZoneFactory
from parking_permits.utils import get_end_time
from users.models import ParkingPermitGroups, User
from users.tests.factories.user import UserFactory

from .services.test_traficom import get_mock_xml


class MockResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


@dataclasses.dataclass
class Info:
    context: dict


@dataclasses.dataclass
class Auth:
    user: User


@pytest.fixture()
def admin_user():
    user = UserFactory()
    user.groups.add(Group.objects.create(name=ParkingPermitGroups.SUPER_ADMIN))
    return user


@pytest.fixture()
def info(rf, admin_user):
    request = rf.get("/")
    request.user = admin_user
    return Info(context={"request": request})


@pytest.fixture()
def mock_jwt(admin_user):
    return unittest.mock.patch(
        "helusers.oidc.RequestJWTAuthentication.authenticate",
        return_value=Auth(user=admin_user),
    )


@pytest.mark.django_db
@freeze_time("2026-11-28")
@pytest.mark.parametrize(
    "end_type, prepaid",
    [("IMMEDIATELY", False), ("AFTER_CURRENT_PERIOD", False), ("IMMEDIATELY", True)],
)
def test_admin_end_recurring_primary(info, mock_jwt, client, end_type, prepaid):
    primary_start = timezone.now().replace(day=1)
    secondary_start = primary_start + relativedelta(weeks=1)
    primary = ParkingPermitFactory(
        status="VALID",
        contract_type="OPEN_ENDED",
        start_time=primary_start,
        end_time=get_end_time(primary_start, 2 if prepaid else 1),
    )
    secondary = ParkingPermitFactory(
        customer=primary.customer,
        primary_vehicle=False,
        status="VALID",
        contract_type="OPEN_ENDED",
        parking_zone=primary.parking_zone,
        start_time=secondary_start,
        end_time=get_end_time(secondary_start, 1),
    )
    product = ProductFactory(
        zone=primary.parking_zone,
        start_date=date(2026, 11, 1),
        end_date=date(2027, 1, 31),
    )
    for permit in (primary, secondary):
        order = OrderFactory(
            customer=primary.customer,
            status=OrderStatus.CONFIRMED,
            paid_time=timezone.now(),
        )
        order.permits.add(permit)
        OrderItemFactory(
            order=order,
            permit=permit,
            product=product,
            quantity=1,
            start_time=permit.start_time,
            end_time=permit.end_time,
        )
    if prepaid:
        renewal = OrderFactory(
            customer=primary.customer,
            status=OrderStatus.CONFIRMED,
            type="SUBSCRIPTION_RENEWED",
            paid_time=timezone.now() + relativedelta(seconds=1),
        )
        renewal.permits.add(primary)
        OrderItemFactory(
            order=renewal,
            permit=primary,
            product=product,
            quantity=1,
            subscription=primary.order_items.get().subscription,
            start_time=primary_start + relativedelta(months=1),
            end_time=primary.end_time,
        )
    order_count = Order.objects.count()
    subscription = secondary.order_items.get().subscription
    with (
        mock_jwt,
        mock.patch("parking_permits.models.order.OrderValidator.validate_order"),
        mock.patch(
            "parking_permits.models.order.Subscription._cancel_talpa_subcription"
        ) as cancel,
        mock.patch("parking_permits.models.order.Order._cancel_talpa_order"),
    ):
        assert admin_resolvers.resolve_end_permit(None, info, primary.pk, end_type) == {
            "success": True
        }
        primary.refresh_from_db()
        secondary.refresh_from_db()
        cancel.assert_called_once()
        if end_type == "AFTER_CURRENT_PERIOD":
            assert primary.status == "VALID"
            assert not secondary.primary_vehicle
            with freeze_time("2026-12-01"):
                automatic_expiration_of_permits()
        primary.refresh_from_db()
        secondary.refresh_from_db()
        assert primary.is_closed
        assert secondary.is_valid and secondary.primary_vehicle
        assert secondary.end_time == get_end_time(secondary_start, 1)
        subscription.refresh_from_db()
        assert subscription.status == "CONFIRMED"
        cancel.assert_called_once()
    assert Order.objects.count() == order_count
    assert not secondary.refunds.exists()
    if prepaid:
        assert primary.refunds.get().amount == Decimal("30")
    else:
        assert not Refund.objects.exists()
    response = client.post(
        reverse("parking_permits:talpa-price"),
        {
            "subscriptionId": str(subscription.talpa_subscription_id),
            "userId": str(secondary.customer.user.uuid),
            "orderItem": {
                "orderItemId": "item",
                "meta": [{"key": "permitId", "value": secondary.pk}],
            },
        },
        content_type="application/json",
    )
    expected = product.get_talpa_pricing(
        is_low_emission=secondary.vehicle.is_low_emission, is_secondary=False
    )
    assert response.json()["priceGross"] == expected["price_gross"]


@pytest.mark.django_db
def test_admin_cannot_end_fixed_primary_with_active_secondary(info, mock_jwt):
    primary = ParkingPermitFactory(status="VALID", contract_type="FIXED_PERIOD")
    ParkingPermitFactory(
        customer=primary.customer,
        primary_vehicle=False,
        status="VALID",
        contract_type="FIXED_PERIOD",
    )
    with mock_jwt, pytest.raises(EndPermitError):
        admin_resolvers.resolve_end_permit(None, info, primary.pk, "IMMEDIATELY")


@pytest.fixture()
def customer_info():
    return {
        "first_name": "Hessu",
        "last_name": "Hessalainen",
        "national_id_number": "290200A905H",
        "primary_address": {
            "postal_code": "00100",
            "city": "Helsinki",
            "city_sv": "Helsingfors",
            "street_name": "Mannerheimintie",
            "street_name_sv": "Mannerheimsgatan",
            "street_number": "5",
            "location": (1000, 1000),
        },
        "primary_address_apartment": "1A",
        "email": "hessu.hessalainen@gmail.com",
        "phone_number": "045 1234 567",
        "address_security_ban": False,
        "driver_license_checked": True,
    }


@pytest.mark.django_db()
def test_update_or_create_new_customer(customer_info):
    customer = update_or_create_customer(customer_info)
    assert customer.national_id_number == "290200A905H"
    assert customer.first_name == "Hessu"
    assert customer.primary_address.street_name == "Mannerheimintie"


@pytest.mark.django_db()
def test_update_or_create_new_customer_missing_primary_address(customer_info):
    del customer_info["primary_address"]
    with pytest.raises(AddressError):
        update_or_create_customer(customer_info)


@pytest.mark.django_db()
def test_update_or_create_new_customer_missing_primary_address_other_address(
    customer_info,
):
    customer_info["other_address"] = customer_info["primary_address"]
    del customer_info["primary_address"]

    customer = update_or_create_customer(customer_info)
    assert customer.national_id_number == "290200A905H"
    assert customer.first_name == "Hessu"
    assert customer.primary_address is None
    assert customer.other_address.street_name == "Mannerheimintie"


@pytest.mark.django_db()
def test_update_or_create_new_customer_address_security_ban(customer_info):
    customer = update_or_create_customer(
        {**customer_info, "address_security_ban": True}
    )
    assert customer.national_id_number == "290200A905H"
    assert customer.first_name == ""
    assert customer.primary_address is None


@pytest.mark.django_db()
def test_update_or_create_new_customer_missing_address_security_ban(customer_info):
    del customer_info["primary_address"]
    customer = update_or_create_customer(
        {**customer_info, "address_security_ban": True}
    )
    assert customer.national_id_number == "290200A905H"
    assert customer.first_name == ""
    assert customer.primary_address is None


@pytest.mark.django_db()
def test_update_or_create_new_customer_hetu_lowercase(customer_info):
    customer = update_or_create_customer(
        {**customer_info, "national_id_number": "290200a905h"}
    )
    assert customer.national_id_number == "290200A905H"
    assert customer.first_name == "Hessu"
    assert customer.primary_address.street_name == "Mannerheimintie"


@pytest.mark.django_db()
def test_update_or_create_existing_customer(customer_info):
    CustomerFactory(national_id_number="290200A905H")
    customer = update_or_create_customer(customer_info)
    assert customer.national_id_number == "290200A905H"
    assert customer.first_name == "Hessu"
    assert customer.primary_address.street_name == "Mannerheimintie"


@pytest.mark.django_db()
@pytest.mark.parametrize("email", ["hessu@example.com.", "hessu@example", "hessu"])
def test_update_or_create_customer_invalid_email(customer_info, email):
    customer_info["email"] = email
    with pytest.raises(InvalidEmailError):
        update_or_create_customer(customer_info)
    assert not Customer.objects.filter(national_id_number="290200A905H").exists()


@pytest.mark.django_db()
def test_update_or_create_customer_strips_email(customer_info):
    customer_info["email"] = "  hessu@example.com "
    customer = update_or_create_customer(customer_info)
    assert customer.email == "hessu@example.com"


@pytest.mark.django_db()
@pytest.mark.parametrize("email", ["", None])
def test_update_or_create_customer_blank_email(customer_info, email):
    customer_info["email"] = email
    customer = update_or_create_customer(customer_info)
    assert customer.email == ""


@pytest.mark.django_db()
def test_add_temporary_vehicle(info, mock_jwt, settings):
    settings.TRAFICOM_MOCK = True
    now = timezone.now()
    permit = ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.OPEN_ENDED,
        start_time=now,
        end_time=now + relativedelta(months=1, days=-1),
        month_count=1,
    )

    vehicle = VehicleFactory()
    start_time = now + relativedelta(days=1)
    end_time = now + relativedelta(days=15)

    with mock_jwt:
        add_temporary_vehicle(
            None,
            info,
            permit.pk,
            vehicle.registration_number,
            start_time.isoformat(),
            end_time.isoformat(),
        )

    temp_vehicle = permit.temp_vehicles.get()
    assert temp_vehicle.vehicle == vehicle
    assert temp_vehicle.start_time == start_time
    assert temp_vehicle.end_time == end_time


def _create_temp_vehicle_permit():
    now = timezone.now()
    return ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.OPEN_ENDED,
        start_time=now,
        end_time=now + relativedelta(months=1, days=-1),
        month_count=1,
    )


@pytest.mark.django_db()
def test_add_temporary_vehicle_permit_not_found(info, mock_jwt, settings):
    settings.TRAFICOM_MOCK = True
    now = timezone.now()

    with mock_jwt, pytest.raises(ObjectNotFoundError):
        add_temporary_vehicle(
            None,
            info,
            0,
            VehicleFactory().registration_number,
            now.isoformat(),
            (now + relativedelta(days=1)).isoformat(),
        )


@pytest.mark.django_db()
def test_add_temporary_vehicle_uses_placeholder_vehicle(
    info, mock_jwt, admin_user, settings
):
    settings.TRAFICOM_MOCK = True
    permit = _create_temp_vehicle_permit()
    now = timezone.now()

    with mock_jwt:
        add_temporary_vehicle(
            None,
            info,
            permit.pk,
            "unknown-1",
            now.isoformat(),
            (now + relativedelta(days=1)).isoformat(),
        )

    temp_vehicle = permit.temp_vehicles.get()
    assert temp_vehicle.vehicle.registration_number == "UNKNOWN-1"
    assert temp_vehicle.vehicle.power_type.identifier == "01"
    assert temp_vehicle.created_by == admin_user


@pytest.mark.django_db()
def test_add_temporary_vehicle_no_limit(info, mock_jwt, settings):
    settings.TRAFICOM_MOCK = True
    permit = _create_temp_vehicle_permit()
    now = timezone.now()
    permit.temp_vehicles.set(
        TemporaryVehicleFactory.create_batch(
            2,
            start_time=now - relativedelta(days=30),
            end_time=now - relativedelta(days=29),
            created_by=permit.customer.user,
            is_active=False,
        )
    )

    with mock_jwt:
        add_temporary_vehicle(
            None,
            info,
            permit.pk,
            VehicleFactory().registration_number,
            now.isoformat(),
            (now + relativedelta(days=1)).isoformat(),
        )

    assert permit.temp_vehicles.count() == 3


@pytest.mark.django_db()
def test_add_temporary_vehicle_writes_audit_log(info, mock_jwt, settings):
    settings.TRAFICOM_MOCK = True
    permit = _create_temp_vehicle_permit()
    now = timezone.now()

    with (
        mock_jwt,
        mock.patch.object(admin_resolvers.audit_logger, "info") as mock_audit_info,
    ):
        # Resolve at call time: other tests may reload admin_resolvers.
        admin_resolvers.add_temporary_vehicle(
            None,
            info,
            permit.pk,
            VehicleFactory().registration_number,
            now.isoformat(),
            (now + relativedelta(days=1)).isoformat(),
        )

    mock_audit_info.assert_called_once()
    audit_msg = mock_audit_info.call_args.args[0]
    assert audit_msg.message == "Admin added a temporary vehicle for a permit."
    assert audit_msg.target == permit


@pytest.mark.django_db()
def test_resolve_get_extended_permit_price_list(info, mock_jwt):
    now = timezone.now()

    permit = ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.FIXED_PERIOD,
        start_time=now,
        end_time=now + relativedelta(days=10),
    )

    ProductFactory(
        zone=permit.parking_zone,
        type=ProductType.RESIDENT,
        start_date=(now - relativedelta(days=360)).date(),
        end_date=(now + relativedelta(days=360)).date(),
    )

    with mock_jwt:
        response = resolve_get_extended_permit_price_list(None, info, permit.pk, 3)

    assert len(list(response)) == 1


@pytest.mark.django_db()
@override_settings(PERMIT_EXTENSIONS_ENABLED=True)
def test_resolve_extend_parking_permit_ok(info, mock_jwt):
    now = timezone.now()
    permit = ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.FIXED_PERIOD,
        start_time=now,
        end_time=now + relativedelta(months=1, days=-1),
        month_count=1,
    )
    permit.address = permit.customer.primary_address
    permit.save()

    ProductFactory(
        zone=permit.parking_zone,
        type=ProductType.RESIDENT,
        start_date=(now - relativedelta(days=360)).date(),
        end_date=(now + relativedelta(days=360)).date(),
    )

    with mock_jwt:
        response = resolve_extend_parking_permit(None, info, str(permit.pk), 3)

    assert response["success"] is True

    assert ParkingPermitExtensionRequest.objects.count() == 1

    ext_request = ParkingPermitExtensionRequest.objects.first()
    assert ext_request.is_approved()
    assert ext_request.month_count == 3
    assert ext_request.permit == permit

    permit.refresh_from_db()
    # 1+3 months
    assert permit.month_count == 4


@pytest.mark.django_db()
@override_settings(PERMIT_EXTENSIONS_ENABLED=True)
def test_resolve_extend_parking_permit_invalid(info, mock_jwt):
    now = timezone.now()
    permit = ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.OPEN_ENDED,
        start_time=now,
        end_time=now + relativedelta(months=1, days=-1),
        month_count=1,
    )

    with mock_jwt:
        with pytest.raises(PermitCanNotBeExtendedError):
            resolve_extend_parking_permit(None, info, str(permit.pk), 3)

    assert ParkingPermitExtensionRequest.objects.count() == 0

    permit.refresh_from_db()
    assert permit.month_count == 1


@pytest.mark.django_db
def test_update_or_create_vehicle_should_create_vehicle():
    power_type = VehiclePowerTypeFactory()
    vehicle_info = dict(
        registration_number="ABC-123",
        manufacturer="Manufacturer",
        model="Model",
        consent_low_emission_accepted=True,
        serial_number="123",
        vehicle_class="M1",
        power_type={"identifier": power_type.identifier},
    )

    vehicle = update_or_create_vehicle(vehicle_info)

    skipped_keys = ["power_type"]
    for k, v in vehicle_info.items():
        if k in skipped_keys:
            continue
        assert getattr(vehicle, k) == v
    assert vehicle.power_type == power_type


@pytest.mark.django_db
def test_update_or_create_vehicle_emission_none():
    power_type = VehiclePowerTypeFactory()
    vehicle_info = dict(
        registration_number="ABC-123",
        manufacturer="Manufacturer",
        model="Model",
        consent_low_emission_accepted=True,
        serial_number="123",
        vehicle_class="M1",
        power_type={"identifier": power_type.identifier},
    )

    vehicle = update_or_create_vehicle(vehicle_info)

    skipped_keys = ["power_type"]
    for k, v in vehicle_info.items():
        if k in skipped_keys:
            continue
        assert getattr(vehicle, k) == v
    assert vehicle.power_type == power_type


@pytest.mark.django_db
def test_update_or_create_vehicle_should_update_vehicle():
    old_power_type = VehiclePowerTypeFactory(identifier="01")
    new_power_type = VehiclePowerTypeFactory(identifier="04")
    old_vehicle = VehicleFactory(
        registration_number="ABC-123",
        power_type=old_power_type,
        manufacturer="jkhlkhjlhljk",
        model="jhkllhjkhljk",
        consent_low_emission_accepted=False,
        serial_number="khjlkhjhjlk",
        vehicle_class="M2",
    )
    vehicle_info = dict(
        registration_number="ABC-123",
        manufacturer="Manufacturer",
        model="Model",
        consent_low_emission_accepted=True,
        serial_number="123",
        vehicle_class="M1",
        power_type={"identifier": new_power_type.identifier},
    )

    new_vehicle = update_or_create_vehicle(vehicle_info)

    assert new_vehicle.id == old_vehicle.id
    skipped_keys = ["registration_number", "power_type"]
    # A bit excessive, but whatever.
    for k, v in vehicle_info.items():
        if k in skipped_keys:
            continue
        assert getattr(old_vehicle, k) != getattr(new_vehicle, k)
        assert getattr(new_vehicle, k) == v

    assert old_vehicle.power_type != new_vehicle.power_type
    assert new_vehicle.power_type == new_power_type


@pytest.mark.django_db
def test_update_or_create_vehicle_should_raise_error_if_power_type_identifier_is_missing():
    vehicle_info = dict(
        registration_number="ABC-123",
        manufacturer="Manufacturer",
        model="Model",
        consent_low_emission_accepted=True,
        serial_number="123",
        vehicle_class="M1",
        power_type={"name": "bar"},
    )

    with pytest.raises(KeyError):
        update_or_create_vehicle(vehicle_info)


@pytest.mark.django_db
def test_update_or_create_vehicle_should_raise_error_if_power_type_is_not_found():
    VehiclePowerTypeFactory(identifier="01")
    vehicle_info = dict(
        registration_number="ABC-123",
        manufacturer="Manufacturer",
        model="Model",
        consent_low_emission_accepted=True,
        serial_number="123",
        vehicle_class="M1",
        power_type={"identifier": "banana"},
    )

    with pytest.raises(ObjectNotFoundError) as exc_info:
        update_or_create_vehicle(vehicle_info)
    assert "Vehicle power type not found" in str(exc_info.value)


@pytest.mark.django_db
@override_settings(
    TRAFICOM_MOCK=False, TRAFICOM_CHECK=True, TRAFICOM_USE_LEGACY_VEHICLE_FETCH=False
)
@mock.patch(
    "requests.Session.post", return_value=MockResponse(get_mock_xml("vehicle_ok.xml"))
)
def test_admin_vehicle_lookup_success(info, mock_jwt):
    # Data from mock XML file
    customer_nin_number = "290200A905H"
    reg_number = "BCI-707"

    # Customer has NO driving license in database
    customer = CustomerFactory(national_id_number=customer_nin_number)
    assert not hasattr(customer, "driving_licence")

    with mock_jwt:
        # Admin should still be able to fetch vehicle
        # Using registration number from mock XML: BCI-707
        vehicle = resolve_vehicle(
            None, info, reg_number=reg_number, national_id_number=customer_nin_number
        )

    # Refresh data to verify that no driving license was added to customer
    customer.refresh_from_db()

    assert vehicle is not None
    assert vehicle.registration_number == reg_number
    assert not hasattr(customer, "driving_licence")


@pytest.mark.django_db
@override_settings(
    TRAFICOM_MOCK=False, TRAFICOM_CHECK=True, TRAFICOM_USE_LEGACY_VEHICLE_FETCH=True
)
@mock.patch(
    "requests.Session.post",
    return_value=MockResponse(get_mock_xml("vehicle_ok.xml", use_legacy_mock_xml=True)),
)
def test_admin_vehicle_lookup_success_on_legacy_api(info, mock_jwt):
    # Data from mock XML file
    customer_nin_number = "290200A905H"
    reg_number = "BCI-707"

    # Customer has NO driving license in database
    customer = CustomerFactory(national_id_number=customer_nin_number)
    assert not hasattr(customer, "driving_licence")

    with mock_jwt:
        # Admin should still be able to fetch vehicle
        # Using registration number from mock XML: BCI-707
        vehicle = resolve_vehicle(
            None, info, reg_number=reg_number, national_id_number=customer_nin_number
        )

    # Refresh data to verify that no driving license was added to customer
    customer.refresh_from_db()

    assert vehicle is not None
    assert vehicle.registration_number == reg_number
    assert not hasattr(customer, "driving_licence")


@pytest.mark.django_db
@override_settings(
    TRAFICOM_MOCK=False, TRAFICOM_CHECK=True, TRAFICOM_USE_LEGACY_VEHICLE_FETCH=False
)
@mock.patch(
    "requests.Session.post",
    return_value=MockResponse(get_mock_xml("vehicle_ok.xml")),
)
def test_admin_vehicle_lookup_fails_for_non_owner(info, mock_jwt):
    non_owner_nin_number = "131052-308T"  # From another mock XML file
    # Customer has NO driving license in database
    CustomerFactory(national_id_number=non_owner_nin_number)

    with mock_jwt:
        # Admin should NOT be able to fetch vehicle for non-owner
        # Using registration number from mock XML: BCI-707
        with pytest.raises(TraficomFetchVehicleError) as exc_info:
            resolve_vehicle(
                None,
                info,
                reg_number="BCI-707",
                national_id_number=non_owner_nin_number,
            )

    assert "Owner/holder data of a vehicle could not be verified" in str(exc_info.value)


@pytest.mark.django_db
@override_settings(
    TRAFICOM_MOCK=False, TRAFICOM_CHECK=True, TRAFICOM_USE_LEGACY_VEHICLE_FETCH=True
)
@mock.patch(
    "requests.Session.post",
    return_value=MockResponse(get_mock_xml("vehicle_ok.xml", use_legacy_mock_xml=True)),
)
def test_admin_vehicle_lookup_fails_for_non_owner_on_legacy_api(info, mock_jwt):
    non_owner_nin_number = "131052-308T"  # From another mock XML file
    # Customer has NO driving license in database
    CustomerFactory(national_id_number=non_owner_nin_number)

    with mock_jwt:
        # Admin should NOT be able to fetch vehicle for non-owner
        # Using registration number from mock XML: BCI-707
        with pytest.raises(TraficomFetchVehicleError) as exc_info:
            resolve_vehicle(
                None,
                info,
                reg_number="BCI-707",
                national_id_number=non_owner_nin_number,
            )

    assert "Owner/holder data of a vehicle could not be verified" in str(exc_info.value)


@pytest.mark.django_db()
@mock.patch("parking_permits.admin_resolvers.update_or_create_vehicle")
@mock.patch("parking_permits.admin_resolvers.update_or_create_customer")
@mock.patch("parking_permits.admin_resolvers.update_or_create_customer_address")
def test_create_resident_permit_sets_vehicle(
    mock_customer_address_upsert,
    mock_customer_upsert,
    mock_vehicle_upsert,
    info,
    mock_jwt,
):
    customer = CustomerFactory()
    vehicle = VehicleFactory()
    zone = ParkingZoneFactory(name="A")

    mock_customer_upsert.return_value = customer
    mock_vehicle_upsert.return_value = vehicle
    mock_customer_address_upsert.return_value = customer.primary_address

    permit_input = {
        "customer": {
            "address_security_ban": customer.address_security_ban,
            "national_id_number": customer.national_id_number,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone_number": customer.phone_number,
            "driver_license_checked": customer.driver_license_checked,
        },
        "vehicle": {"registration_number": "ABC-123"},
        "zone": zone.name,
        "start_time": "2024-01-01T00:00:00+00:00",
        "month_count": 1,
        "status": ParkingPermitStatus.DRAFT,
        "description": "",
        "address_apartment": "1A",
        "bypass_traficom_validation": True,
    }

    with mock_jwt:
        result = resolve_create_resident_permit(None, info, permit_input)

    permit = result["permit"]
    permit.refresh_from_db()
    assert permit.vehicle is not None
    assert permit.vehicle == vehicle


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    [
        ParkingPermitStatus.DRAFT,
        ParkingPermitStatus.PRELIMINARY,
        ParkingPermitStatus.PAYMENT_IN_PROGRESS,
        ParkingPermitStatus.VALID,
    ],
)
def test_staff_cannot_add_fixed_permit_to_subscription(
    info, mock_jwt, customer_info, status
):
    customer = update_or_create_customer(customer_info)
    subscription = ParkingPermitFactory(
        customer=customer, status=status, contract_type=ContractType.OPEN_ENDED
    )
    with mock_jwt, pytest.raises(CreatePermitError):
        resolve_create_resident_permit(None, info, {"customer": customer_info})
    assert list(customer.permits.all()) == [subscription]
    assert not Order.objects.exists()


@pytest.mark.django_db
def test_staff_cannot_quote_or_apply_zone_change_for_mixed_permits(info, mock_jwt):
    permit = ParkingPermitFactory(
        status=ParkingPermitStatus.VALID, contract_type=ContractType.OPEN_ENDED
    )
    other = ParkingPermitFactory(
        customer=permit.customer,
        primary_vehicle=False,
        status=ParkingPermitStatus.VALID,
        contract_type=ContractType.FIXED_PERIOD,
        parking_zone=permit.parking_zone,
    )
    data = {
        "customer": {"national_id_number": permit.customer.national_id_number},
        "vehicle": {"registration_number": permit.vehicle.registration_number},
        "zone": ParkingZoneFactory().name,
    }
    old_zone = permit.parking_zone_id
    with mock_jwt:
        for resolver in (
            resolve_permit_price_change_list,
            resolve_update_resident_permit,
        ):
            with pytest.raises(UpdatePermitError):
                resolver(None, info, permit.pk, data)
    for item in (permit, other):
        item.refresh_from_db()
        assert item.parking_zone_id == old_zone
    assert not Order.objects.exists()
    assert not Refund.objects.exists()


@pytest.mark.django_db()
@pytest.mark.parametrize(
    "edit, status",
    [
        ("vehicle", ParkingPermitStatus.VALID),
        ("vehicle", ParkingPermitStatus.DRAFT),
        ("vehicle", ParkingPermitStatus.PRELIMINARY),
        ("vehicle", ParkingPermitStatus.PAYMENT_IN_PROGRESS),
        ("classification", ParkingPermitStatus.VALID),
        ("metadata", ParkingPermitStatus.VALID),
        ("pending zone", ParkingPermitStatus.VALID),
    ],
)
@mock.patch("parking_permits.models.ParkingPermit.get_price_change_list")
@mock.patch("parking_permits.admin_resolvers.update_or_create_vehicle")
@mock.patch("parking_permits.admin_resolvers.update_or_create_customer_address")
def test_update_resident_permit_sets_new_vehicle(
    mock_customer_address_upsert,
    mock_vehicle_upsert,
    mock_price_change,
    info,
    mock_jwt,
    edit,
    status,
):
    old_vehicle = VehicleFactory(
        registration_number="OLD-111", power_type__identifier="01"
    )
    new_vehicle = (
        VehicleFactory(registration_number="NEW-222")
        if edit == "vehicle"
        else old_vehicle
    )
    permit = ParkingPermitFactory(
        vehicle=old_vehicle,
        contract_type=ContractType.FIXED_PERIOD,
        status=status,
    )
    if edit == "classification":

        def update_vehicle(_):
            new_vehicle.power_type = VehiclePowerTypeFactory(identifier="04")
            new_vehicle.save()
            return new_vehicle

        mock_vehicle_upsert.side_effect = update_vehicle
    zone = permit.parking_zone
    if edit == "pending zone":
        zone = ParkingZoneFactory()
        ParkingPermitFactory(
            customer=permit.customer,
            primary_vehicle=False,
            parking_zone=permit.parking_zone,
            contract_type=ContractType.FIXED_PERIOD,
            status=ParkingPermitStatus.PAYMENT_IN_PROGRESS,
        )

    mock_vehicle_upsert.return_value = new_vehicle
    # No price delta => no order creation branch.
    mock_price_change.return_value = []
    mock_customer_address_upsert.return_value = permit.customer.primary_address

    permit_info = {
        "customer": {
            "address_security_ban": permit.customer.address_security_ban,
            "national_id_number": permit.customer.national_id_number,
            "first_name": permit.customer.first_name,
            "last_name": permit.customer.last_name,
            "email": permit.customer.email,
            "phone_number": permit.customer.phone_number,
            "driver_license_checked": permit.customer.driver_license_checked,
            "primary_address": {
                "postal_code": permit.customer.primary_address.postal_code,
                "city": permit.customer.primary_address.city,
                "city_sv": permit.customer.primary_address.city_sv,
                "street_name": permit.customer.primary_address.street_name,
                "street_name_sv": permit.customer.primary_address.street_name_sv,
                "street_number": permit.customer.primary_address.street_number,
                "location": (
                    permit.customer.primary_address.location.x,
                    permit.customer.primary_address.location.y,
                ),
            },
        },
        "vehicle": {"registration_number": new_vehicle.registration_number},
        "zone": zone.name,
        "start_time": "2024-01-01T00:00:00+00:00",
        "month_count": 1,
        "description": "",
        "address_apartment": "1A",
        "bypass_traficom_validation": True,
        "status": permit.status,
    }

    with mock_jwt:
        if edit == "pending zone" or status == ParkingPermitStatus.PAYMENT_IN_PROGRESS:
            for resolver in (
                resolve_permit_price_change_list,
                resolve_update_resident_permit,
            ):
                with pytest.raises(
                    UpdatePermitError, match="Resolve the pending checkout"
                ):
                    resolver(None, info, permit.id, permit_info)
            mock_price_change.assert_not_called()
            permit.refresh_from_db()
            assert permit.vehicle == old_vehicle
            if edit == "pending zone":
                mock_vehicle_upsert.assert_not_called()
                assert permit.parking_zone != zone
            return
        if status != ParkingPermitStatus.VALID:
            assert (
                resolve_permit_price_change_list(None, info, permit.id, permit_info)
                == []
            )
        resolve_update_resident_permit(None, info, permit.id, permit_info)
    if status == ParkingPermitStatus.VALID and edit != "metadata":
        mock_price_change.assert_called_once()
    else:
        mock_price_change.assert_not_called()
    permit.refresh_from_db()
    assert permit.vehicle == new_vehicle
    assert permit.status == status


class TalpaMockResponse:
    reasons = {401: "Forbidden"}

    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self.reason = self.reasons.get(status_code)
        self.json_data = json_data
        self.text = "Error" if status_code != 200 else ""

    def json(self):
        return self.json_data


def _product_input(zone_name):
    return {
        "type": ProductType.RESIDENT,
        "zone": zone_name,
        "unit_price": Decimal(30),
        "unit": "MONTHLY",
        "start_date": date(2024, 1, 1),
        "end_date": date(2024, 12, 31),
        "vat_percentage": 25.5,
        "low_emission_discount_percentage": 50,
    }


@pytest.mark.django_db()
@override_settings(
    TALPA_DEFAULT_ACCOUNTING_COMPANY_CODE="1234",
    TALPA_DEFAULT_ACCOUNTING_VAT_CODE="AAA",
    TALPA_DEFAULT_ACCOUNTING_INTERNAL_ORDER="internal-order",
    TALPA_DEFAULT_ACCOUNTING_PROFIT_CENTER="profit-center",
    TALPA_DEFAULT_ACCOUNTING_BALANCE_PROFIT_CENTER="balance-profit-center",
    TALPA_DEFAULT_ACCOUNTING_PROJECT="project",
    TALPA_DEFAULT_ACCOUNTING_OPERATION_AREA="operation-area",
    TALPA_DEFAULT_ACCOUNTING_MAIN_LEDGER_ACCOUNT="main-ledger-account",
)
@mock.patch(
    "requests.post",
    return_value=TalpaMockResponse(201, {"productId": uuid.uuid4()}),
)
@mock.patch(
    "requests.get",
    return_value=TalpaMockResponse(200, {"0": {"merchantId": uuid.uuid4()}}),
)
def test_create_product_stamps_new_accounting(mock_get, mock_post, info, mock_jwt):
    zone = ParkingZoneFactory(name="A")

    with mock_jwt:
        resolve_create_product(None, info, _product_input(zone.name))

    product = Product.objects.get(zone=zone)
    admin_user = info.context["request"].user
    assert product.accounting is not None
    assert product.accounting.created_by == admin_user
    assert product.accounting.modified_by == admin_user


@pytest.mark.django_db()
@override_settings(
    TALPA_DEFAULT_ACCOUNTING_COMPANY_CODE="1234",
    TALPA_DEFAULT_ACCOUNTING_VAT_CODE="AAA",
    TALPA_DEFAULT_ACCOUNTING_INTERNAL_ORDER="internal-order",
    TALPA_DEFAULT_ACCOUNTING_PROFIT_CENTER="profit-center",
    TALPA_DEFAULT_ACCOUNTING_BALANCE_PROFIT_CENTER="balance-profit-center",
    TALPA_DEFAULT_ACCOUNTING_PROJECT="project",
    TALPA_DEFAULT_ACCOUNTING_OPERATION_AREA="operation-area",
    TALPA_DEFAULT_ACCOUNTING_MAIN_LEDGER_ACCOUNT="main-ledger-account",
)
@mock.patch(
    "requests.post",
    return_value=TalpaMockResponse(201, {"productId": uuid.uuid4()}),
)
@mock.patch(
    "requests.get",
    return_value=TalpaMockResponse(200, {"0": {"merchantId": uuid.uuid4()}}),
)
def test_create_product_does_not_overwrite_reused_accounting_stamps(
    mock_get, mock_post, info, mock_jwt
):
    zone = ParkingZoneFactory(name="B")
    original_creator = UserFactory()
    # matches the overridden TALPA_DEFAULT_ACCOUNTING_* settings above, so
    # create_talpa_accounting() will reuse this row instead of creating a
    # new one
    existing_accounting = Accounting.objects.create(
        company_code="1234",
        vat_code="AAA",
        internal_order="internal-order",
        profit_center="profit-center",
        balance_profit_center="balance-profit-center",
        project="project",
        operation_area="operation-area",
        main_ledger_account="main-ledger-account",
        created_by=original_creator,
        modified_by=original_creator,
    )

    with mock_jwt:
        resolve_create_product(None, info, _product_input(zone.name))

    product = Product.objects.get(zone=zone)
    assert product.accounting_id == existing_accounting.pk

    existing_accounting.refresh_from_db()
    # the reused accounting's original audit provenance must be preserved,
    # not overwritten with the admin creating the new product
    assert existing_accounting.created_by == original_creator
    assert existing_accounting.modified_by == original_creator


@pytest.mark.django_db
@freeze_time("2026-05-25")
@pytest.mark.parametrize(
    "edit, expected_price",
    [
        ("replace vehicle", "80.00"),
        ("correct power type", "40.00"),
        ("move address", "90.00"),
    ],
)
def test_staff_subscription_edits_take_effect_at_renewal(
    info, mock_jwt, customer_info, client, edit, expected_price
):
    # The next month has already been paid. Saving an edit must leave that payment intact.
    old_power = "04" if edit == "replace vehicle" else "01"
    address = customer_info["primary_address"]
    old_zone = ParkingZoneFactory()
    address["location"] = old_zone.location.centroid.coords
    permit = ParkingPermitFactory(
        parking_zone=old_zone,
        contract_type=ContractType.OPEN_ENDED,
        status=ParkingPermitStatus.VALID,
        vehicle__power_type__identifier=old_power,
        address=admin_resolvers.update_or_create_address(address),
        start_time=timezone.now().replace(month=4, day=1),
        end_time=timezone.now().replace(month=6, day=30, hour=20, minute=59),
    )
    customer_info["national_id_number"] = permit.customer.national_id_number
    old_product = ProductFactory(
        zone=old_zone,
        type=ProductType.RESIDENT,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 5, 31),
        unit_price=Decimal("60"),
    )
    paid_price = Decimal("30" if old_power == "04" else "60")
    order = OrderFactory(
        customer=permit.customer, status=OrderStatus.CONFIRMED, paid_time=timezone.now()
    )
    order.permits.add(permit)
    item = OrderItemFactory(
        permit=permit,
        order=order,
        product=old_product,
        quantity=1,
        unit_price=paid_price,
        payment_unit_price=paid_price,
        talpa_order_item_id=uuid.uuid4(),
    )
    subscription_id = item.subscription_id

    vehicle = permit.vehicle
    zone = old_zone
    if edit == "replace vehicle":
        vehicle = VehicleFactory(power_type__identifier="01")
    elif edit == "move address":
        zone = ParkingZoneFactory()
        customer_info["primary_address"] = {
            **address,
            "street_name": "New street",
            "location": zone.location.centroid.coords,
        }
    vehicle_input = {
        key: getattr(vehicle, key)
        for key in (
            "registration_number",
            "manufacturer",
            "model",
            "serial_number",
            "vehicle_class",
            "consent_low_emission_accepted",
        )
    }
    power = (
        VehiclePowerTypeFactory(identifier="04")
        if edit == "correct power type"
        else vehicle.power_type
    )
    vehicle_input["power_type"] = {"identifier": power.identifier}
    data = {
        "customer": customer_info,
        "address": customer_info["primary_address"],
        "zone": zone.name,
        "vehicle": vehicle_input,
        "status": permit.status,
        "description": permit.description,
    }

    with mock_jwt:
        assert resolve_permit_price_change_list(None, info, permit.pk, data) == []
        assert resolve_update_resident_permit(None, info, permit.pk, data) == {
            "success": True
        }

    permit.refresh_from_db()
    item.refresh_from_db()
    assert permit.vehicle.registration_number == vehicle.registration_number
    assert permit.vehicle.power_type == power
    assert permit.address.street_name == data["address"]["street_name"]
    assert permit.parking_zone == zone
    assert list(Order.objects.all()) == [order]
    assert list(permit.order_items.all()) == [item]
    assert item.subscription_id == subscription_id
    assert item.payment_unit_price == paid_price
    assert not item.is_refunded
    assert not Refund.objects.exists()

    # Talpa asks for the price later, after a new tariff has taken effect.
    ProductFactory(
        zone=zone,
        type=ProductType.RESIDENT,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 12, 31),
        unit_price=Decimal("90" if edit == "move address" else "80"),
        low_emission_discount=Decimal("0.5"),
    )
    with freeze_time("2026-06-25"):
        response = client.post(
            reverse("parking_permits:talpa-price"),
            {
                "userId": str(permit.customer.user.uuid),
                "subscriptionId": str(item.subscription.talpa_subscription_id),
                "orderItem": {
                    "orderItemId": str(item.talpa_order_item_id),
                    "meta": [{"key": "permitId", "value": str(permit.pk)}],
                },
            },
            content_type="application/json",
        )
    assert response.status_code == 200
    assert response.json()["priceGross"] == expected_price


@pytest.mark.django_db
@freeze_time(timezone.make_aware(datetime(2024, 4, 29, 12, 0)))
@pytest.mark.parametrize(
    "edit, renewing",
    [
        ("vehicle", "edited"),
        ("vehicle", "other"),
        ("address", "edited"),
        ("address", "other"),
        ("zone", "edited"),
        ("zone", "other"),
        ("power_type", "edited"),
        ("metadata", "edited"),
    ],
)
@mock.patch("parking_permits.models.ParkingPermit.get_price_change_list")
@mock.patch("parking_permits.admin_resolvers.update_or_create_vehicle")
@mock.patch("parking_permits.admin_resolvers.update_or_create_customer_address")
@mock.patch("parking_permits.admin_resolvers.update_or_create_address")
def test_staff_can_change_vehicle_or_address_during_renewal_period(
    mock_address_upsert,
    mock_customer_address_upsert,
    mock_vehicle_upsert,
    mock_price_change,
    info,
    mock_jwt,
    edit,
    renewing,
):
    renewal_end = timezone.make_aware(datetime(2024, 4, 30, 23, 59, 59))
    normal_end = timezone.make_aware(datetime(2024, 5, 14, 23, 59, 59))
    zone = ParkingZoneFactory()

    def open_ended(customer=None, end_time=normal_end, **kwargs):
        if customer:
            kwargs["customer"] = customer
        return ParkingPermitFactory(
            contract_type=ContractType.OPEN_ENDED,
            status=ParkingPermitStatus.VALID,
            parking_zone=zone,
            start_time=end_time - relativedelta(days=30),
            end_time=end_time,
            month_count=1,
            **kwargs,
        )

    permit = open_ended(end_time=renewal_end if renewing == "edited" else normal_end)
    other = open_ended(
        customer=permit.customer,
        primary_vehicle=False,
        end_time=renewal_end if renewing == "other" else normal_end,
    )
    old_vehicle, old_address = permit.vehicle, permit.address
    new_vehicle = VehicleFactory() if edit == "vehicle" else old_vehicle
    new_address = AddressFactory() if edit == "address" else old_address
    new_zone = ParkingZoneFactory() if edit == "zone" else zone
    mock_vehicle_upsert.return_value = new_vehicle
    mock_address_upsert.return_value = new_address
    mock_customer_address_upsert.return_value = new_address
    mock_price_change.return_value = []

    customer = permit.customer
    data = {
        "customer": {
            "address_security_ban": False,
            "national_id_number": customer.national_id_number,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone_number": customer.phone_number,
            "driver_license_checked": customer.driver_license_checked,
            "primary_address": {"street_name": new_address.street_name},
        },
        "vehicle": {
            "registration_number": new_vehicle.registration_number,
            "manufacturer": "Updated"
            if edit == "metadata"
            else old_vehicle.manufacturer,
            "power_type": {
                "identifier": (
                    "04" if edit == "power_type" else old_vehicle.power_type.identifier
                )
            },
        },
        "zone": new_zone.name,
        "status": permit.status,
        "description": "updated" if edit == "metadata" else permit.description,
    }

    order_count = Order.objects.count()
    refund_count = Refund.objects.count()

    with mock_jwt:
        assert resolve_update_resident_permit(None, info, permit.pk, data) == {
            "success": True
        }

    permit.refresh_from_db()
    other.refresh_from_db()
    assert permit.vehicle == new_vehicle
    assert permit.address == other.address == new_address
    assert permit.parking_zone == other.parking_zone == new_zone
    # The next period already charged by Talpa keeps its original price.
    assert Order.objects.count() == order_count
    assert Refund.objects.count() == refund_count
