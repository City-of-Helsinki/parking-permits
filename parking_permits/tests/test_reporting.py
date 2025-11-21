import itertools
import math
from datetime import date, datetime, time

from dateutil.relativedelta import relativedelta
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APITestCase
from rest_framework_api_key.models import APIKey

from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus
from parking_permits.models.reporting import PermitCountSnapshot
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.vehicle import (
    VehicleFactory,
    VehiclePowerTypeFactory,
)
from parking_permits.tests.factories.zone import ParkingZoneFactory


class PermitCountSnapshotTestCase(TestCase):

    def test_creating_duplicate_permit_count_snapshot_raises(self):

        test_date = date(2024, 11, 30)

        def create_snapshot(*, count: int):
            PermitCountSnapshot.objects.create(
                permit_count=count,
                date=test_date,
                parking_zone_name="A",
                parking_zone_description="Kallio",
                parking_zone_description_sv="Berghäll",
                low_emission=True,
                primary_vehicle=True,
                contract_type=ContractType.OPEN_ENDED,
            )

        create_snapshot(count=0)
        with self.assertRaises(IntegrityError):
            create_snapshot(count=2)

    def test_build_daily_permit_count_snapshot(self):

        test_date = date(2024, 11, 30)
        # First day of the previous month from test_date
        permit_start_date = (test_date - relativedelta(months=2)) + relativedelta(
            days=1
        )
        # Last day of the next month from test_date
        permit_end_date = test_date + relativedelta(months=1)
        permit_start_time = datetime.combine(permit_start_date, time(0, 0, 0))
        permit_end_time = datetime.combine(permit_end_date, time(23, 59, 59))

        zone_a = ParkingZoneFactory(
            name="A",
            description="Kallio",
            description_sv="Berghäll",
        )
        zone_b = ParkingZoneFactory(
            name="B",
            description="Etu-Töölö",
            description_sv="Främre Tölö",
        )

        # NOTE: identifier="04" makes this grant low-emission-status
        # for the vehicle
        electric_power_type = VehiclePowerTypeFactory(identifier="04")
        non_electric_power_type = VehiclePowerTypeFactory(identifier="01")
        low_emission_vehicle = VehicleFactory(power_type=electric_power_type)
        high_emission_vehicle = VehicleFactory(power_type=non_electric_power_type)

        # generate a different count of permits for all the different dimension value combinations:
        parking_zones = (
            zone_a,
            zone_b,
        )
        vehicles = (
            low_emission_vehicle,
            high_emission_vehicle,
        )
        contract_types = (
            ContractType.FIXED_PERIOD,
            ContractType.OPEN_ENDED,
        )
        vehicle_primarity = (
            True,
            False,
        )

        dimension_lists = (
            parking_zones,
            vehicles,
            contract_types,
            vehicle_primarity,
        )

        combination_count = math.prod(len(dim_list) for dim_list in dimension_lists)
        for count_to_create, dimensions in enumerate(
            itertools.product(*dimension_lists), start=1
        ):
            for _ in range(count_to_create):
                ParkingPermitFactory(
                    status=ParkingPermitStatus.VALID,
                    start_time=permit_start_time,
                    end_time=permit_end_time,
                    parking_zone=dimensions[0],
                    vehicle=dimensions[1],
                    contract_type=dimensions[2],
                    primary_vehicle=dimensions[3],
                )

        # Run the snapshot-building logic on test_date
        with freeze_time(
            timezone.make_aware(
                datetime(test_date.year, test_date.month, test_date.day, 22)
            )
        ):
            call_command("create_daily_permit_counts")

            now = timezone.now()
            now_date = now.date()

        permit_count_data = PermitCountSnapshot.objects.filter(date=now_date)
        self.assertEqual(len(permit_count_data), combination_count)

        # Check that a snapshot exists for all the expected
        # permit count values. (from 1 to the total amount of dimension
        # combinations, inclusive from both ends.)
        # NOTE: we're relying heavily here on the unique-constraint on
        # the PermitCountSnapshot-model as it guarantees that the
        # different counts correspond to different dimension value
        # combinations.
        for target_count in range(1, combination_count + 1):
            self.assertTrue(
                permit_count_data.filter(permit_count=target_count).exists()
            )

        # Run the snapshot-building logic on test_date _AGAIN_
        # to force updates over creates
        with freeze_time(
            timezone.make_aware(
                datetime(test_date.year, test_date.month, test_date.day, 22)
            )
        ):
            call_command("create_daily_permit_counts")

        # Re-fetch data after running the updates on the snapshots
        permit_count_data = PermitCountSnapshot.objects.filter(date=now_date)

        # Previus assertions should still hold as we're just updating
        # the daily counts with unchanged permit data
        self.assertEqual(len(permit_count_data), combination_count)
        for target_count in range(1, combination_count + 1):
            self.assertTrue(
                permit_count_data.filter(permit_count=target_count).exists()
            )


class PermitCountSnapshotViewTestCase(APITestCase):

    url = reverse("parking_permits:permit-count-snapshot-list")

    @classmethod
    def setUpTestData(cls):
        PermitCountSnapshot.objects.create(
            permit_count=4,
            date=date(2024, 11, 30),
            parking_zone_name="A",
            parking_zone_description="Kallio",
            parking_zone_description_sv="Berghäll",
            low_emission=True,
            primary_vehicle=True,
            contract_type=ContractType.OPEN_ENDED,
        )
        PermitCountSnapshot.objects.create(
            permit_count=12,
            date=date(2025, 10, 31),
            parking_zone_name="B",
            parking_zone_description="Etu-Töölö",
            parking_zone_description_sv="Främre Tölö",
            low_emission=False,
            primary_vehicle=False,
            contract_type=ContractType.FIXED_PERIOD,
        )

    def assert_failing_api_key_request(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.reason_phrase, "Forbidden")
        self.assertEqual(list(response.data.keys()), ["detail"])
        error = str(response.data["detail"])
        self.assertEqual(error, "Authentication credentials were not provided.")

    def assert_successful_api_read(self, response):
        self.assertEqual(response.status_code, 200)
        expected_data = [
            {
                "permit_count": 4,
                "date": "2024-11-30",
                "parking_zone_name": "A",
                "parking_zone_description": "Kallio",
                "parking_zone_description_sv": "Berghäll",
                "low_emission": True,
                "primary_vehicle": True,
                "contract_type": "OPEN_ENDED",
            },
            {
                "permit_count": 12,
                "date": "2025-10-31",
                "parking_zone_name": "B",
                "parking_zone_description": "Etu-Töölö",
                "parking_zone_description_sv": "Främre Tölö",
                "low_emission": False,
                "primary_vehicle": False,
                "contract_type": "FIXED_PERIOD",
            },
        ]
        self.assertEqual(response.data, expected_data)

    def test_permit_count_snapshot_list_view_with_valid_api_key(self):
        key_string = APIKey.objects.create_key(name="valid key")[1]
        headers = {"Authorization": f"Api-Key {key_string}"}
        response = self.client.get(self.url, headers=headers)
        self.assert_successful_api_read(response)

    def test_permit_count_snapshot_list_view_without_api_key(self):
        response = self.client.get(self.url)
        self.assert_failing_api_key_request(response)

    def test_permit_count_snapshot_list_view_with_invalid_api_key(self):
        key_string = "SomethingResemblingAValidApiKey"
        headers = {"Authorization": f"Api-Key {key_string}"}
        response = self.client.get(self.url, headers=headers)
        self.assert_failing_api_key_request(response)

    def test_permit_count_snapshot_list_view_with_revoked_api_key(self):
        key_instance, key_string = APIKey.objects.create_key(name="revoked key")

        key_instance.revoked = True
        key_instance.save()

        headers = {"Authorization": f"Api-Key {key_string}"}
        response = self.client.get(self.url, headers=headers)
        self.assert_failing_api_key_request(response)

    def test_permit_count_snapshot_list_view_with_expired_api_key(self):
        key_creation_date = datetime(2025, 11, 30, 0, 0, 0)
        key_expiration_time = datetime(2026, 11, 30, 0, 0, 0)
        with freeze_time(timezone.make_aware(key_creation_date)):
            key_string = APIKey.objects.create_key(
                name="expired key", expiry_date=key_expiration_time
            )[1]

        auth_attempt_date = key_expiration_time + relativedelta(days=1)

        with freeze_time(timezone.make_aware(auth_attempt_date)):
            headers = {"Authorization": f"Api-Key {key_string}"}
            response = self.client.get(self.url, headers=headers)
            self.assert_failing_api_key_request(response)
