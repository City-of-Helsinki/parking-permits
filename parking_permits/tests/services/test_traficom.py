import datetime
import pathlib
from unittest import mock

from django.test import TestCase, override_settings
from freezegun import freeze_time

from parking_permits.exceptions import TraficomFetchVehicleError
from parking_permits.models import DrivingClass, DrivingLicence
from parking_permits.models.vehicle import EmissionType
from parking_permits.services.traficom import Traficom
from parking_permits.tests.factories import LowEmissionCriteriaFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.vehicle import VehicleFactory


class MockResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


def get_mock_xml(filename):
    return (
        (pathlib.Path(__file__).parent / "mocks" / "traficom" / filename)
        .open("r")
        .read()
    )


class TestTraficom(TestCase):
    registration_number = "BCI-707"
    hetu = "290200A905H"

    @classmethod
    def setUpTestData(cls):
        cls.traficom = Traficom()

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle(self):
        with mock.patch(
            "requests.post", return_value=MockResponse(get_mock_xml("vehicle_ok.xml"))
        ):
            vehicle = self.traficom.fetch_vehicle_details("BCI-707")
            self.assertEqual(vehicle.registration_number, "BCI-707")

            # Euro-class and emissions
            assert vehicle.euro_class == 6
            assert vehicle.emission_type == EmissionType.NEDC
            assert vehicle.emission == 155

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_lower_case(self):
        with mock.patch(
            "requests.post", return_value=MockResponse(get_mock_xml("vehicle_ok.xml"))
        ):
            vehicle = self.traficom.fetch_vehicle_details("bci-707")
            self.assertEqual(vehicle.registration_number, "BCI-707")

            # Euro-class and emissions
            assert vehicle.euro_class == 6
            assert vehicle.emission_type == EmissionType.NEDC
            assert vehicle.emission == 155

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_with_spaces(self):
        with mock.patch(
            "requests.post", return_value=MockResponse(get_mock_xml("vehicle_ok.xml"))
        ):
            vehicle = self.traficom.fetch_vehicle_details("BCI-707   ")
            self.assertEqual(vehicle.registration_number, "BCI-707")

            # Euro-class and emissions
            assert vehicle.euro_class == 6
            assert vehicle.emission_type == EmissionType.NEDC
            assert vehicle.emission == 155

    # TODO: Replace this with more specific L3eA1, L3eA2, L3eA3 tests
    #  (and remove light_weight_vehicle.xml)
    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_light_weight_vehicle(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("light_weight_vehicle.xml")),
        ):
            registration_number = "NV-298"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)
            # TODO: Add different test users with driving licence A, A1, A2
            #  and check that all test users have driving licence for this vehicle
            # self.assertTrue(
            #    user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
            #        vehicle
            #    )
            # )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.weight, 244)

    # TODO: Replace this test case with more specific L3eA1, L3eA2, L3eA3 tests
    #  (and remove light_weight_vehicle_L3e.xml)
    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_light_weight_vehicle_L3e(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("light_weight_vehicle_L3e.xml")),
        ):
            registration_number = "GN-347"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)
            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.weight, 220)

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_too_heavy(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("vehicle_too_heavy.xml")),
        ):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                "BCI-707",
            )

    @override_settings(TRAFICOM_MOCK=False)
    @freeze_time(datetime.datetime(2024, 6, 1))
    def test_fetch_vehicle_without_emissions(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("vehicle_without_emissions.xml")),
        ):
            LowEmissionCriteriaFactory(
                nedc_max_emission_limit=37,
                wltp_max_emission_limit=50,
                start_date=datetime.datetime(2024, 1, 1),
                end_date=datetime.datetime(2024, 12, 31),
                euro_min_class_limit=6,
            )

            vehicle = self.traficom.fetch_vehicle_details("BCI-707")
            self.assertEqual(vehicle.registration_number, "BCI-707")
            self.assertEqual(vehicle.emission, 0)
            self.assertEqual(vehicle.euro_class, 5)
            self.assertEqual(vehicle.is_low_emission, False)

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_wltp(self):
        with mock.patch(
            "requests.post", return_value=MockResponse(get_mock_xml("vehicle_wltp.xml"))
        ):
            vehicle = self.traficom.fetch_vehicle_details("BCI-707")
            self.assertEqual(vehicle.registration_number, "BCI-707")

            # Emissions
            assert vehicle.emission_type == EmissionType.WLTP
            assert vehicle.emission == 155

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_nedc(self):
        with mock.patch(
            "requests.post", return_value=MockResponse(get_mock_xml("vehicle_nedc.xml"))
        ):
            vehicle = self.traficom.fetch_vehicle_details("111-500")
            self.assertEqual(vehicle.registration_number, "111-500")

            # Emissions
            assert vehicle.emission_type == EmissionType.NEDC
            assert vehicle.emission == 13

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_already_exists(self):
        vehicle = VehicleFactory(registration_number="BCI-707")

        with mock.patch(
            "requests.post", return_value=MockResponse(get_mock_xml("vehicle_ok.xml"))
        ):
            fetched_vehicle = self.traficom.fetch_vehicle_details("BCI-707")
            self.assertEqual(fetched_vehicle, vehicle)

    @override_settings(TRAFICOM_MOCK=False)
    def test_traficom_api_error(self):
        with mock.patch("requests.post", return_value=MockResponse(status_code=500)):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                "BCI-707",
            )

    @override_settings(TRAFICOM_MOCK=False)
    def test_vehicle_not_found(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("vehicle_not_found.xml")),
        ):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                "BCI-707",
            )

    @override_settings(TRAFICOM_MOCK=False)
    def test_unsupported_vehicle_class(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("unsupported_vehicle.xml")),
        ):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                "BCI-707",
            )

    @override_settings(TRAFICOM_MOCK=False)
    def test_vehicle_decommissioned(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("decommissioned_vehicle.xml")),
        ):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                "BCI-707",
            )

    @override_settings(TRAFICOM_MOCK=True)
    def test_fetch_vehicle_from_db(self):
        VehicleFactory(registration_number="BCI-707")
        with mock.patch("requests.post") as mock_traficom:
            vehicle = self.traficom.fetch_vehicle_details("BCI-707")
            self.assertEqual(vehicle.registration_number, "BCI-707")
            mock_traficom.assert_not_called()

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_from_db_if_permit_bypass_true(self):
        VehicleFactory(registration_number="BCI-707")
        permit = ParkingPermitFactory(bypass_traficom_validation=True)
        with mock.patch("requests.post") as mock_traficom:
            vehicle = self.traficom.fetch_vehicle_details("BCI-707", permit)
            self.assertEqual(vehicle.registration_number, "BCI-707")
            mock_traficom.assert_not_called()

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_from_db_if_permit_bypass_false(self):
        permit = ParkingPermitFactory(bypass_traficom_validation=False)
        with mock.patch(
            "requests.post", return_value=MockResponse(get_mock_xml("vehicle_ok.xml"))
        ) as mock_traficom:
            vehicle = self.traficom.fetch_vehicle_details("BCI-707", permit)
            self.assertEqual(vehicle.registration_number, "BCI-707")
            mock_traficom.assert_called()

    @override_settings(TRAFICOM_MOCK=True)
    def test_fetch_vehicle_from_db_not_found(self):
        with mock.patch("requests.post") as mock_traficom:
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                "BCI-707",
            )

            mock_traficom.assert_not_called()

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_valid_licence(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("licence_ok.xml")),
        ):
            result = self.traficom.fetch_driving_licence_details(self.hetu)
            self.assertEqual(len(result["driving_classes"]), 7)
            self.assertEqual(result["issue_date"], "2023-09-01")

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_invalid_licence(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("invalid_licence.xml")),
        ):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_driving_licence_details,
                self.hetu,
            )

    @override_settings(TRAFICOM_MOCK=True)
    def test_fetch_licence_from_db(self):
        customer = CustomerFactory(national_id_number=self.hetu)
        licence = DrivingLicence.objects.create(
            customer=customer,
            start_date=datetime.date(2023, 6, 3),
        )
        assert licence.start_date == datetime.date(2023, 6, 3)
        driving_class = DrivingClass.objects.create(identifier="A")
        licence.driving_classes.add(driving_class)

        with mock.patch("requests.post") as mock_traficom:
            result = self.traficom.fetch_driving_licence_details(self.hetu)
            self.assertEqual(result["issue_date"], licence.start_date)
            self.assertEqual(result["driving_classes"].count(), 1)
            mock_traficom.assert_not_called()

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_licence_from_db_if_permit_bypass(self):
        customer = CustomerFactory(national_id_number=self.hetu)
        permit = ParkingPermitFactory(
            customer=customer, bypass_traficom_validation=True
        )
        licence = DrivingLicence.objects.create(
            customer=customer,
            start_date=datetime.date(2023, 6, 3),
        )
        assert licence.start_date == datetime.date(2023, 6, 3)
        driving_class = DrivingClass.objects.create(identifier="A")
        licence.driving_classes.add(driving_class)

        with mock.patch("requests.post") as mock_traficom:
            result = self.traficom.fetch_driving_licence_details(self.hetu, permit)
            self.assertEqual(result["issue_date"], licence.start_date)
            self.assertEqual(result["driving_classes"].count(), 1)
            mock_traficom.assert_not_called()

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_valid_licence_if_not_permit_bypass(self):
        customer = CustomerFactory(national_id_number=self.hetu)
        permit = ParkingPermitFactory(
            customer=customer, bypass_traficom_validation=False
        )
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("licence_ok.xml")),
        ) as mock_traficom:
            result = self.traficom.fetch_driving_licence_details(self.hetu, permit)
            self.assertEqual(len(result["driving_classes"]), 7)
            self.assertEqual(result["issue_date"], "2023-09-01")
            mock_traficom.assert_called()

    @override_settings(TRAFICOM_MOCK=True)
    def test_fetch_licence_from_db_not_found(self):
        with mock.patch("requests.post") as mock_traficom:
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_driving_licence_details,
                self.hetu,
            )

            mock_traficom.assert_not_called()
