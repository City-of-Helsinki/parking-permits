import datetime

from django.test import TestCase
from freezegun import freeze_time

from parking_permits.models.vehicle import (
    EmissionType,
    LowEmissionCriteria,
    VehiclePowerType,
    is_low_emission_vehicle,
)
from parking_permits.tests.factories import LowEmissionCriteriaFactory
from parking_permits.tests.factories.vehicle import VehicleFactory


@freeze_time(datetime.datetime(2020, 6, 1))
class TestIsLowEmissionVehicle(TestCase):
    def setUp(self):
        self.lec = LowEmissionCriteriaFactory(
            power_type=VehiclePowerType.DIESEL,
            nedc_max_emission_limit=100,
            wltp_max_emission_limit=100,
            start_date=datetime.datetime(2020, 1, 1),
            end_date=datetime.datetime(2020, 12, 31),
            euro_min_class_limit=5,
        )

        self.vehicle = VehicleFactory(
            power_type=VehiclePowerType.DIESEL,
            emission_type=EmissionType.NEDC,
            emission=50,
            euro_class=10,
        )
        self.assertIsLowEmissionVehicle(self.vehicle, True)

    def assertIsLowEmissionVehicle(self, vehicle, is_low_emission: bool):
        self.assertEqual(
            is_low_emission_vehicle(
                vehicle.power_type,
                vehicle.euro_class,
                vehicle.emission_type,
                vehicle.emission,
            ),
            is_low_emission,
        )

    def test_should_return_true_if_power_type_is_electric(self):
        vehicle = VehicleFactory(
            power_type=VehiclePowerType.ELECTRIC,
        )

        self.assertIsLowEmissionVehicle(vehicle, True)

    def test_should_return_false_if_low_emission_criteria_is_not_found(self):
        self.vehicle.power_type = VehiclePowerType.BENSIN

        self.assertIsLowEmissionVehicle(self.vehicle, False)

    def test_should_return_false_if_euro_class_is_falsey(self):
        self.vehicle.euro_class = None

        self.assertIsLowEmissionVehicle(self.vehicle, False)

    def test_should_return_false_if_emission_is_none(self):
        self.vehicle.emission = None

        self.assertIsLowEmissionVehicle(self.vehicle, False)

    def test_should_return_false_if_euro_class_below_min_class_limit(self):
        self.vehicle.euro_class = 1

        self.assertIsLowEmissionVehicle(self.vehicle, False)

    def test_emission_type_nedc_should_return_true_if_at_or_below_max_emission_limit(
        self,
    ):
        self.vehicle.emission_type = EmissionType.NEDC

        # emission < max limit
        self.vehicle.emission = 0
        self.assertIsLowEmissionVehicle(self.vehicle, True)

        # emission == max limit
        self.vehicle.emission = self.lec.nedc_max_emission_limit
        self.assertIsLowEmissionVehicle(self.vehicle, True)

    def test_emission_type_nedc_should_return_false_if_above_max_emission_limit(self):
        self.vehicle.emission_type = EmissionType.NEDC
        self.vehicle.emission = self.lec.nedc_max_emission_limit + 1

        self.assertIsLowEmissionVehicle(self.vehicle, False)

    def test_emission_type_wltp_should_return_true_if_at_or_below_max_emission_limit(
        self,
    ):
        self.vehicle.emission_type = EmissionType.WLTP

        # emission < max limit
        self.vehicle.emission = 0
        self.assertIsLowEmissionVehicle(self.vehicle, True)

        # emission == max limit
        self.vehicle.emission = self.lec.wltp_max_emission_limit
        self.assertIsLowEmissionVehicle(self.vehicle, True)

    def test_emission_type_wltp_should_return_false_if_above_max_emission_limit(self):
        self.vehicle.emission_type = EmissionType.WLTP
        self.vehicle.emission = self.lec.wltp_max_emission_limit + 1

        self.assertIsLowEmissionVehicle(self.vehicle, False)

    def test_should_return_false_by_default(self):
        self.vehicle.emission_type = ""

        self.assertIsLowEmissionVehicle(self.vehicle, False)


class TestVehicle(TestCase):
    def test_should_update_is_low_emission_field_on_save(self):
        vehicle = VehicleFactory(
            power_type=VehiclePowerType.DIESEL,
        )
        LowEmissionCriteria.objects.all().delete()

        # Check that both the computed property and field are false before we start.
        self.assertFalse(vehicle.is_low_emission)
        self.assertFalse(vehicle._is_low_emission)

        vehicle.power_type = VehiclePowerType.ELECTRIC

        # Only the computed property should be true at this point.
        self.assertTrue(vehicle.is_low_emission)
        self.assertFalse(vehicle._is_low_emission)

        vehicle.save()

        # Both should be true after saving.
        self.assertTrue(vehicle.is_low_emission)
        self.assertTrue(vehicle._is_low_emission)
