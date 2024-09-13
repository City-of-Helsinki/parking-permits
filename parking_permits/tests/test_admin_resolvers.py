import dataclasses
import unittest

import pytest
from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import Group
from django.test import override_settings
from django.utils import timezone

from parking_permits.admin_resolvers import (
    add_temporary_vehicle,
    resolve_extend_parking_permit,
    resolve_get_extended_permit_price_list,
    update_or_create_customer,
    update_or_create_vehicle,
)
from parking_permits.exceptions import (
    AddressError,
    ObjectNotFound,
    PermitCanNotBeExtended,
)
from parking_permits.models import ParkingPermitExtensionRequest
from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus
from parking_permits.models.product import ProductType
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import (
    VehicleFactory,
    VehiclePowerTypeFactory,
)
from users.models import ParkingPermitGroups, User
from users.tests.factories.user import UserFactory


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
        with pytest.raises(PermitCanNotBeExtended):
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
        euro_class=1,
        emission=1,
        emission_type="WLTP",
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
        euro_class=1,
        emission=None,
        emission_type="WLTP",
        power_type={"identifier": power_type.identifier},
    )

    vehicle = update_or_create_vehicle(vehicle_info)

    skipped_keys = ["power_type", "emission"]
    for k, v in vehicle_info.items():
        if k in skipped_keys:
            continue
        assert getattr(vehicle, k) == v
    assert vehicle.emission == 0
    assert vehicle.power_type == power_type


@pytest.mark.django_db
def test_update_or_create_vehicle_should_update_vehicle():
    old_power_type = VehiclePowerTypeFactory()
    new_power_type = VehiclePowerTypeFactory()
    old_vehicle = VehicleFactory(
        registration_number="ABC-123",
        power_type=old_power_type,
        manufacturer="jkhlkhjlhljk",
        model="jhkllhjkhljk",
        consent_low_emission_accepted=False,
        serial_number="khjlkhjhjlk",
        vehicle_class="M2",
        euro_class=10000,
        emission=10000,
        emission_type="NEDC",
    )
    vehicle_info = dict(
        registration_number="ABC-123",
        manufacturer="Manufacturer",
        model="Model",
        consent_low_emission_accepted=True,
        serial_number="123",
        vehicle_class="M1",
        euro_class=1,
        emission=1,
        emission_type="WLTP",
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
        euro_class=1,
        emission=1,
        emission_type="WLTP",
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
        euro_class=1,
        emission=1,
        emission_type="WLTP",
        power_type={"identifier": "banana"},
    )

    with pytest.raises(ObjectNotFound) as exc_info:
        update_or_create_vehicle(vehicle_info)
    assert "Vehicle power type not found" in str(exc_info.value)
