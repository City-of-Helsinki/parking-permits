import datetime
import pathlib
from unittest import mock

from django.test import TestCase, override_settings

from parking_permits.exceptions import TraficomFetchVehicleError
from parking_permits.models import DrivingClass, DrivingLicence
from parking_permits.models.vehicle import EmissionType
from parking_permits.services.traficom import Traficom
from parking_permits.tests.factories.customer import CustomerFactory
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
            vehicle = self.traficom.fetch_vehicle_details(self.registration_number)
            self.assertEqual(vehicle.registration_number, self.registration_number)

            # Emissions
            assert vehicle.emission_type == EmissionType.NEDC
            assert vehicle.emission == 155.00

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_too_heavy(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("vehicle_too_heavy.xml")),
        ):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                self.registration_number,
            )

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_wltp(self):
        with mock.patch(
            "requests.post", return_value=MockResponse(get_mock_xml("vehicle_wltp.xml"))
        ):
            vehicle = self.traficom.fetch_vehicle_details(self.registration_number)
            self.assertEqual(vehicle.registration_number, self.registration_number)

            # Emissions
            assert vehicle.emission_type == EmissionType.WLTP
            assert vehicle.emission == 155.00

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_nedc(self):
        with mock.patch(
            "requests.post", return_value=MockResponse(get_mock_xml("vehicle_nedc.xml"))
        ):
            vehicle = self.traficom.fetch_vehicle_details(self.registration_number)
            self.assertEqual(vehicle.registration_number, self.registration_number)

            # Emissions
            assert vehicle.emission_type == EmissionType.NEDC
            assert vehicle.emission == 13.00

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_already_exists(self):
        vehicle = VehicleFactory(registration_number=self.registration_number)

        with mock.patch(
            "requests.post", return_value=MockResponse(get_mock_xml("vehicle_ok.xml"))
        ):
            fetched_vehicle = self.traficom.fetch_vehicle_details(
                self.registration_number
            )
            self.assertEqual(fetched_vehicle, vehicle)

    @override_settings(TRAFICOM_MOCK=False)
    def test_traficom_api_error(self):
        with mock.patch("requests.post", return_value=MockResponse(status_code=500)):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                self.registration_number,
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
                self.registration_number,
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
                self.registration_number,
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
                self.registration_number,
            )

    @override_settings(TRAFICOM_MOCK=True)
    def test_fetch_vehicle_from_db(self):
        VehicleFactory(registration_number=self.registration_number)
        with mock.patch("requests.post") as mock_traficom:
            vehicle = self.traficom.fetch_vehicle_details(self.registration_number)
            self.assertEqual(vehicle.registration_number, self.registration_number)
            mock_traficom.assert_not_called()

    @override_settings(TRAFICOM_MOCK=True)
    def test_fetch_vehicle_from_db_not_found(self):
        with mock.patch("requests.post") as mock_traficom:
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                self.registration_number,
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

    @override_settings(TRAFICOM_MOCK=True)
    def test_fetch_licence_from_db_not_found(self):
        with mock.patch("requests.post") as mock_traficom:
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_driving_licence_details,
                self.hetu,
            )

            mock_traficom.assert_not_called()
