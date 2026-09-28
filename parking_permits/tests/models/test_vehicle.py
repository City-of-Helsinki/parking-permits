import datetime

from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from parking_permits.models.vehicle import is_low_emission_vehicle
from parking_permits.tests.factories.vehicle import (
    TemporaryVehicleFactory,
    VehicleFactory,
    VehiclePowerTypeFactory,
)


@freeze_time(datetime.datetime(2024, 3, 1, 9, 0))
class TestTemporaryVehicle(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.temp_vehicle = TemporaryVehicleFactory(
            start_time=now, end_time=now + datetime.timedelta(days=7)
        )

    def test_period_range(self):
        self.assertEqual(
            self.temp_vehicle.period_range,
            (
                self.temp_vehicle.start_time,
                self.temp_vehicle.end_time,
            ),
        )


@freeze_time(datetime.datetime(2020, 6, 1))
class TestIsLowEmissionVehicle(TestCase):
    def setUp(self):
        self.power_type_diesel = VehiclePowerTypeFactory(name="Diesel", identifier="02")
        self.vehicle = VehicleFactory(
            power_type=self.power_type_diesel,
        )
        self.assert_is_low_emission_vehicle(self.vehicle, False)

    def assert_is_low_emission_vehicle(self, vehicle, is_low_emission: bool):
        self.assertEqual(
            is_low_emission_vehicle(vehicle.power_type),
            is_low_emission,
        )

    def test_should_return_true_if_power_type_is_electric(self):
        vehicle = VehicleFactory(
            power_type=VehiclePowerTypeFactory(name="Electric", identifier="04"),
        )

        self.assert_is_low_emission_vehicle(vehicle, True)

    def test_should_return_false_by_default(self):
        self.assert_is_low_emission_vehicle(self.vehicle, False)


class TestVehicle(TestCase):
    def test_string_representation_intentionally_includes_registration_number(
        self,
    ):
        """Unlike Customer.__str__, Vehicle.__str__ intentionally
        keeps the registration number.

        It is relied on as the customer-facing checkout/Talpa product
        label (Vehicle.description) and is rendered directly in permit
        and temporary-vehicle e-mail templates, so customers can see
        their own vehicle's plate number. Do not strip it here without
        also updating those customer-facing usages.
        """
        vehicle = VehicleFactory(registration_number="ABC-123")

        self.assertIn("ABC-123", str(vehicle))
        self.assertIn("ABC-123", vehicle.description)
