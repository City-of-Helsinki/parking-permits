import pytest

from parking_permits.admin_resolvers import update_or_create_vehicle
from parking_permits.exceptions import ObjectNotFound
from parking_permits.tests.factories.vehicle import (
    VehicleFactory,
    VehiclePowerTypeFactory,
)


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
