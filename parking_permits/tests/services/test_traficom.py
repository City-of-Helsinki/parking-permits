import datetime
import pathlib
from unittest import mock

from django.test import TestCase, override_settings
from freezegun import freeze_time

from parking_permits.exceptions import TraficomFetchVehicleError
from parking_permits.models import DrivingClass, DrivingLicence
from parking_permits.models.vehicle import EmissionType, VehicleClass
from parking_permits.services.traficom import Traficom
from parking_permits.tests.factories import LowEmissionCriteriaFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.vehicle import VehicleFactory


class MockResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


def get_mock_xml(filename, encoding="latin-1"):
    return (
        (pathlib.Path(__file__).parent / "mocks" / "traficom" / filename)
        .open("r", encoding=encoding)
        .read()
    )


class TestTraficom(TestCase):
    registration_number = "BCI-707"
    hetu = "290200A905H"

    @classmethod
    def setUpTestData(cls):
        cls.traficom = Traficom()

        cls.user_with_driving_licence_A1 = CustomerFactory()
        cls.user_with_driving_licence_A2 = CustomerFactory()
        cls.user_with_driving_licence_A = CustomerFactory()

        driving_class_A1 = DrivingClass.objects.create(identifier="A1")
        driving_class_A2 = DrivingClass.objects.create(identifier="A2")
        driving_class_A = DrivingClass.objects.create(identifier="A")

        licence_A1 = DrivingLicence.objects.create(
            customer=cls.user_with_driving_licence_A1,
            start_date=datetime.date(2023, 6, 3),
        )
        licence_A2 = DrivingLicence.objects.create(
            customer=cls.user_with_driving_licence_A2,
            start_date=datetime.date(2023, 6, 3),
        )
        licence_A = DrivingLicence.objects.create(
            customer=cls.user_with_driving_licence_A,
            start_date=datetime.date(2023, 6, 3),
        )

        licence_A1.driving_classes.add(driving_class_A1)
        licence_A2.driving_classes.add(driving_class_A2)
        licence_A.driving_classes.add(driving_class_A)

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

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3_subclass_108_licence_A_A1_A2(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3_subclass_108_licence_A_A1_A2.xml")
            ),
        ):
            registration_number = "OB-120"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertTrue(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA1)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3_subclass_109_licence_A_A1_A2(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3_subclass_109_licence_A_A1_A2.xml")
            ),
        ):
            registration_number = "GT-407"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertTrue(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA1)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3_subclass_109_licence_A_A2(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3_subclass_109_licence_A_A2.xml")
            ),
        ):
            registration_number = "84-VHJ"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA2)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3_subclass_109_licence_A(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3_subclass_109_licence_A.xml")
            ),
        ):
            registration_number = "IT-236"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertFalse(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA3)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3_subclass_111_licence_A(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3_subclass_111_licence_A.xml")
            ),
        ):
            registration_number = "FT-479"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertFalse(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA3)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_108_licence_A_A1_A3(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_108_licence_A_A1_A3.xml")
            ),
        ):
            registration_number = "71-AKY"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertTrue(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA1)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_109_licence_A_A1_A2(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_109_licence_A_A1_A2.xml")
            ),
        ):
            registration_number = "77-ALH"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertTrue(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA1)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_109_licence_A_A2(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_109_licence_A_A2.xml")
            ),
        ):
            registration_number = "61-BOR"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA2)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_109_licence_A(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_109_licence_A.xml")
            ),
        ):
            registration_number = "35-AKX"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertFalse(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA3)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_111_licence_A_A2(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_111_licence_A_A2.xml")
            ),
        ):
            registration_number = "71-ECF"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA2)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_900_licence_A_A1_A2(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_900_licence_A_A1_A2.xml")
            ),
        ):
            registration_number = "12-AKZ"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertTrue(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA1)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_905_licence_A_A2(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_905_licence_A_A2.xml")
            ),
        ):
            registration_number = "74-AKY"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA2)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_906_licence_A(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_906_licence_A.xml")
            ),
        ):
            registration_number = "68-AKY"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertFalse(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA3)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_907_licence_A_A1_A2(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_907_licence_A_A1_A2.xml")
            ),
        ):
            registration_number = "CR-397"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertTrue(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA1)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_908_licence_A_A2(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_908_licence_A_A2.xml")
            ),
        ):
            registration_number = "26-LHI"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA2)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_909_licence_A(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_909_licence_A.xml")
            ),
        ):
            registration_number = "62-LHJ"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertFalse(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA3)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_909_licence_A_without_power(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_909_licence_A_without_power.xml")
            ),
        ):
            registration_number = "62-LHJ"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertFalse(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA3)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_subclass_909_licence_A_missing_field(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_subclass_909_licence_A_missing_field.xml")
            ),
        ):
            registration_number = "62-LHJ"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertFalse(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertFalse(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA3)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_L3e_no_subclass_or_power(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(
                get_mock_xml("vehicle_L3e_no_subclass_or_power.xml")
            ),
        ):
            registration_number = "71-ECF"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertTrue(
                self.user_with_driving_licence_A1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A2.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                self.user_with_driving_licence_A.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.L3eA1)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_aoa_2(self):
        # Special chars in registration number
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("special_cases/AOA-2.xml", "utf-8")),
        ):
            registration_number = "ÄÖÅ-2"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertEqual(vehicle.registration_number, registration_number)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_aoa_3(self):
        # Special chars in registration number
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("special_cases/AOA-3.xml", "utf-8")),
        ):
            registration_number = "ÄÖÅ-3"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertEqual(vehicle.registration_number, registration_number)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_abc_12(self):
        # No valid registration
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("special_cases/ABC-12.xml")),
        ):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                "ABC-12",
            )

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_lai_1(self):
        # Regular valid test
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("special_cases/LAI-1.xml")),
        ):
            registration_number = "LAI-1"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertEqual(vehicle.registration_number, registration_number)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_moi_10(self):
        # Person has a non-disclosure statement
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("special_cases/MOI-10.xml")),
        ):

            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                "MOI-10",
            )

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
    def test_fetch_vehicle_with_nedc_and_wltp(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("vehicle_nedc_and_wltp.xml")),
        ):
            LowEmissionCriteriaFactory(
                nedc_max_emission_limit=37,
                wltp_max_emission_limit=50,
                start_date=datetime.datetime(2024, 1, 1),
                end_date=datetime.datetime(3000, 12, 31),
                euro_min_class_limit=6,
            )
            vehicle = self.traficom.fetch_vehicle_details("111-500")
            self.assertEqual(vehicle.registration_number, "111-500")

            assert vehicle.emission_type == EmissionType.WLTP
            assert vehicle.emission == 50
            assert vehicle._is_low_emission

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_vehicle_with_nedc_and_wltp_no_criteria(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("vehicle_nedc_and_wltp.xml")),
        ):
            vehicle = self.traficom.fetch_vehicle_details("111-500")
            self.assertEqual(vehicle.registration_number, "111-500")

            assert vehicle.emission_type == EmissionType.NEDC
            assert vehicle.emission == 53

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

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_valid_c_licence(self):
        customer = CustomerFactory(national_id_number=self.hetu)

        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("licence_C.xml")),
        ):
            expected_licences = ["C", "C1", "C1E", "CE"]

            result = customer.fetch_driving_licence_detail()
            driving_classes = result[0].driving_classes.all()

            for driving_class, licence in zip(driving_classes, expected_licences):
                self.assertEqual(driving_class.identifier, licence)

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_valid_d_licence(self):
        customer = CustomerFactory(national_id_number=self.hetu)

        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("licence_D.xml")),
        ):
            expected_licences = ["D", "D1", "D1E", "DE"]

            result = customer.fetch_driving_licence_detail()
            driving_classes = result[0].driving_classes.all()

            for driving_class, licence in zip(driving_classes, expected_licences):
                self.assertEqual(driving_class.identifier, licence)

    @override_settings(TRAFICOM_MOCK=False)
    def test_fetch_valid_b_licence(self):
        customer = CustomerFactory(national_id_number=self.hetu)

        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("licence_B.xml")),
        ):
            expected_licences = ["B", "BE", "B/96"]

            result = customer.fetch_driving_licence_detail()
            driving_classes = result[0].driving_classes.all()

            for driving_class, licence in zip(driving_classes, expected_licences):
                self.assertEqual(driving_class.identifier, licence)

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=True)
    def test_fetch_vehicle_C1_licence_C_C1_C1E_CE(self):
        user_with_driving_licence_C = CustomerFactory()
        user_with_driving_licence_C1 = CustomerFactory()
        user_with_driving_licence_C1E = CustomerFactory()
        user_with_driving_licence_CE = CustomerFactory()

        driving_class_C = DrivingClass.objects.create(identifier="C")
        driving_class_C1 = DrivingClass.objects.create(identifier="C1")
        driving_class_C1E = DrivingClass.objects.create(identifier="C1E")
        driving_class_CE = DrivingClass.objects.create(identifier="CE")

        licence_C = DrivingLicence.objects.create(
            customer=user_with_driving_licence_C,
            start_date=datetime.date(2023, 6, 3),
        )
        licence_C1 = DrivingLicence.objects.create(
            customer=user_with_driving_licence_C1,
            start_date=datetime.date(2023, 6, 3),
        )
        licence_C1E = DrivingLicence.objects.create(
            customer=user_with_driving_licence_C1E,
            start_date=datetime.date(2023, 6, 3),
        )
        licence_CE = DrivingLicence.objects.create(
            customer=user_with_driving_licence_CE,
            start_date=datetime.date(2023, 6, 3),
        )

        licence_C.driving_classes.add(driving_class_C)
        licence_C1.driving_classes.add(driving_class_C1)
        licence_C1E.driving_classes.add(driving_class_C1E)
        licence_CE.driving_classes.add(driving_class_CE)

        with mock.patch(
            "requests.post",
            return_value=MockResponse(get_mock_xml("vehicle_C1.xml")),
        ):
            registration_number = "FNI-586"
            vehicle = self.traficom.fetch_vehicle_details(registration_number)

            self.assertTrue(
                user_with_driving_licence_C.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                user_with_driving_licence_C1.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                user_with_driving_licence_C1E.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )
            self.assertTrue(
                user_with_driving_licence_CE.has_valid_driving_licence_for_vehicle(
                    vehicle
                )
            )

            self.assertEqual(vehicle.registration_number, registration_number)
            self.assertEqual(vehicle.vehicle_class, VehicleClass.N2)
