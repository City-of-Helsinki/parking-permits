from unittest.mock import patch

import factory
from django.test import TestCase

from parking_permits.exceptions import UnknownAddressSecurityBanValueError
from parking_permits.models.common import SourceSystem
from parking_permits.models.customer import Languages
from parking_permits.services.dvv import (
    _parse_security_ban,
    get_addresses,
    get_person_info,
    is_same_address,
)
from parking_permits.tests.factories.customer import AddressFactory, CustomerFactory
from parking_permits.tests.factories.zone import (
    ParkingZoneFactory,
    generate_multi_polygon,
)
from parking_permits.utils import to_dict
from users.tests.factories.user import UserFactory


class GetPersonInfoTestCase(TestCase):
    class MockResponse:
        def __init__(self, *, data=None, ok=True, text=""):
            self.data = data
            self.ok = ok
            self.text = text

        def json(self):
            return self.data

    def _create_known_customer(self, *, user, zone, primary_address, other_address):
        return CustomerFactory(
            source_system=SourceSystem.HELSINKI_PROFILE,
            source_id="known-source-id",
            user=user,
            first_name="Known First",
            last_name="Known Last",
            national_id_number="010199-1234",
            primary_address=primary_address,
            primary_address_apartment="A1",
            primary_address_apartment_sv="A1 sv",
            other_address=other_address,
            other_address_apartment="B2",
            other_address_apartment_sv="B2 sv",
            email="known@example.com",
            phone_number="0401234567",
            address_security_ban=True,
            driver_license_checked=True,
            zone=zone,
            language=Languages.SWEDISH,
            is_anonymized=True,
        )

    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_bad_response(self, mock_request_person_info, mock_get_access_token):
        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(ok=False, text="oops")
        customer = get_person_info("12345")
        self.assertEqual(customer, None)

    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_logs_customer_id_instead_of_national_id_number(
        self, mock_request_person_info, mock_get_access_token
    ):
        national_id_number = "12345"
        customer = CustomerFactory(national_id_number=national_id_number)
        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(
            ok=False, text=f"response contains {national_id_number}"
        )

        with self.assertLogs("db", level="INFO") as logs:
            get_person_info(national_id_number)

        log_output = "\n".join(logs.output)
        self.assertIn(f"customer_id={customer.id}", log_output)
        self.assertNotIn(national_id_number, log_output)

    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_logs_unknown_customer_without_national_id_number(
        self, mock_request_person_info, mock_get_access_token
    ):
        national_id_number = "12345"
        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(
            ok=False, text=national_id_number
        )

        with self.assertLogs("db", level="INFO") as logs:
            get_person_info(national_id_number)

        log_output = "\n".join(logs.output)
        self.assertIn("customer_id=unknown", log_output)
        self.assertNotIn(national_id_number, log_output)

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_get_customer_info(
        self, mock_request_person_info, mock_get_access_token, mock_get_address_details
    ):
        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(
            data=self.get_mock_info()
        )
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}
        customer = get_person_info("12345")
        self.assertEqual(customer["first_name"], "Heikki")
        self.assertEqual(customer["last_name"], "Häkkinen")
        self.assertEqual(customer["primary_address"]["street_name"], "Käsivoide")
        self.assertEqual(customer["primary_address"]["street_number"], "1")
        self.assertEqual(customer["primary_address"]["postal_code"], "10001")
        self.assertEqual(customer["primary_address"]["city"], "Helsinki")
        self.assertEqual(customer["primary_address_apartment"], "A6")
        self.assertEqual(customer["other_address_apartment"], "B7")

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_get_customer_info_apartment_not_included(
        self, mock_request_person_info, mock_get_access_token, mock_get_address_details
    ):
        mock_info = self.get_mock_info()
        mock_info["Henkilo"]["VakinainenKotimainenLahiosoite"]["LahiosoiteS"] = (
            "Käsivoide 1"
        )
        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(data=mock_info)
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}
        customer = get_person_info("12345")
        self.assertEqual(customer["first_name"], "Heikki")
        self.assertEqual(customer["last_name"], "Häkkinen")
        self.assertEqual(customer["primary_address"]["street_name"], "Käsivoide")
        self.assertEqual(customer["primary_address"]["street_number"], "1")
        self.assertEqual(customer["primary_address"]["postal_code"], "10001")
        self.assertEqual(customer["primary_address"]["city"], "Helsinki")
        self.assertEqual(customer["primary_address_apartment"], "")

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_get_customer_info_addresses_not_in_helsinki(
        self, mock_request_person_info, mock_get_access_token, mock_get_address_details
    ):
        mock_info = self.get_mock_info()
        mock_info["Henkilo"]["VakinainenKotimainenLahiosoite"]["PostitoimipaikkaS"] = (
            "Vantaa"
        )
        mock_info["Henkilo"]["TilapainenKotimainenLahiosoite"]["PostitoimipaikkaS"] = (
            "Espoo"
        )
        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(data=mock_info)
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}
        customer = get_person_info("12345")
        self.assertEqual(customer["first_name"], "Heikki")
        self.assertEqual(customer["last_name"], "Häkkinen")
        self.assertEqual(customer["primary_address"], None)
        self.assertEqual(customer["primary_address_apartment"], "")
        self.assertEqual(customer["other_address"], None)
        self.assertEqual(customer["other_address_apartment"], "")

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_mock_customer_info_null_swedish_address(
        self, mock_request_person_info, mock_get_access_token, mock_get_address_details
    ):
        mock_info = self.get_mock_info()
        mock_info["Henkilo"]["VakinainenKotimainenLahiosoite"]["LahiosoiteR"] = None

        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(data=mock_info)
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}
        customer = get_person_info("12345")
        self.assertEqual(customer["first_name"], "Heikki")
        self.assertEqual(customer["last_name"], "Häkkinen")
        self.assertEqual(customer["primary_address"]["street_name"], "Käsivoide")
        self.assertEqual(customer["primary_address"]["street_name_sv"], "")
        self.assertEqual(customer["primary_address"]["street_number"], "1")
        self.assertEqual(customer["primary_address"]["postal_code"], "10001")
        self.assertEqual(customer["primary_address"]["city"], "Helsinki")
        self.assertEqual(customer["primary_address_apartment"], "A6")

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_get_customer_info_with_empty_address_data(
        self, mock_request_person_info, mock_get_access_token, mock_get_address_details
    ):
        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(
            data=self.get_mock_info_empty_addresses()
        )
        mock_get_address_details.side_effect = AssertionError(
            "get_address_details should not be called for empty address data"
        )
        customer = get_person_info("12345")
        self.assertEqual(customer["first_name"], "Ossi")
        self.assertEqual(customer["last_name"], "Oksanen")
        self.assertEqual(customer["primary_address"], None)
        self.assertEqual(customer["primary_address_apartment"], "")
        self.assertEqual(customer["other_address"], None)
        self.assertEqual(customer["other_address_apartment"], "")

    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_security_ban_known_value_literal_one_returns_blank_customer_data(
        self, mock_request_person_info, mock_get_access_token
    ):
        mock_info = self.get_mock_info()
        mock_info["Henkilo"]["Turvakielto"]["TurvakieltoTieto"] = "1"
        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(data=mock_info)

        customer = get_person_info("12345")

        self.assertEqual(
            customer,
            {
                "national_id_number": "12345",
                "first_name": "",
                "last_name": "",
                "primary_address": None,
                "primary_address_apartment": "",
                "other_address": None,
                "other_address_apartment": "",
                "phone_number": "",
                "email": "",
                "address_security_ban": True,
                "driver_license_checked": False,
                "active_permits": [],
            },
        )

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_security_ban_known_value_none_returns_full_customer_data(
        self, mock_request_person_info, mock_get_access_token, mock_get_address_details
    ):
        mock_info = self.get_mock_info()
        mock_info["Henkilo"]["Turvakielto"]["TurvakieltoTieto"] = None
        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(data=mock_info)
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}

        customer = get_person_info("12345")

        self.assertEqual(customer["address_security_ban"], False)
        self.assertEqual(customer["first_name"], "Heikki")
        self.assertEqual(customer["primary_address"]["street_name"], "Käsivoide")
        self.assertEqual(customer["primary_address"]["street_name"], "Käsivoide")
        self.assertEqual(customer["primary_address"]["street_name_sv"], "Handkrem")
        self.assertEqual(customer["primary_address"]["street_number"], "1")
        self.assertEqual(customer["primary_address"]["postal_code"], "10001")
        self.assertEqual(customer["primary_address"]["city"], "Helsinki")
        self.assertEqual(customer["primary_address"]["city_sv"], "Helsingfors")
        self.assertEqual(customer["primary_address_apartment"], "A6")
        self.assertEqual(customer["other_address"]["street_name"], "Käsivoide")
        self.assertEqual(customer["other_address"]["street_name_sv"], "Handkrem")
        self.assertEqual(customer["other_address"]["street_number"], "6")
        self.assertEqual(customer["other_address"]["postal_code"], "10001")
        self.assertEqual(customer["other_address"]["city"], "Helsinki")
        self.assertEqual(customer["other_address"]["city_sv"], "Helsingfors")
        self.assertEqual(customer["other_address_apartment"], "B7")
        self.assertEqual(customer["phone_number"], "")
        self.assertEqual(customer["email"], "")
        self.assertEqual(customer["driver_license_checked"], False)
        self.assertEqual(customer["active_permits"], [])

    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_active_security_ban_clears_customer_security_fields_in_database(
        self, mock_request_person_info, mock_get_access_token
    ):
        user = UserFactory()
        zone = ParkingZoneFactory()
        primary_address = AddressFactory(street_name="Known Primary Street")
        other_address = AddressFactory(street_name="Known Other Street")
        customer = self._create_known_customer(
            user=user,
            zone=zone,
            primary_address=primary_address,
            other_address=other_address,
        )

        mock_info = self.get_mock_info()
        mock_info["Henkilo"]["Turvakielto"]["TurvakieltoTieto"] = "1"
        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(data=mock_info)

        get_person_info(customer.national_id_number)
        customer.refresh_from_db()

        cleared_fields = {
            "first_name": "",
            "last_name": "",
            "phone_number": "",
            "primary_address_id": None,
            "primary_address_apartment": "",
            "primary_address_apartment_sv": "",
            "other_address_id": None,
            "other_address_apartment": "",
            "other_address_apartment_sv": "",
        }
        for field_name, expected_value in cleared_fields.items():
            with self.subTest(field=field_name):
                self.assertEqual(getattr(customer, field_name), expected_value)

        retained_fields = {
            "source_system": SourceSystem.HELSINKI_PROFILE,
            "source_id": "known-source-id",
            "user_id": user.id,
            "national_id_number": "010199-1234",
            "email": "known@example.com",
            "address_security_ban": True,
            "driver_license_checked": True,
            "zone_id": zone.id,
            "language": Languages.SWEDISH,
            "is_anonymized": True,
        }
        for field_name, expected_value in retained_fields.items():
            with self.subTest(field=field_name):
                self.assertEqual(getattr(customer, field_name), expected_value)

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_no_active_security_ban_does_not_clear_customer_record_in_database(
        self, mock_request_person_info, mock_get_access_token, mock_get_address_details
    ):
        user = UserFactory()
        zone = ParkingZoneFactory()
        primary_address = AddressFactory(street_name="Known Primary Street")
        other_address = AddressFactory(street_name="Known Other Street")
        customer = self._create_known_customer(
            user=user,
            zone=zone,
            primary_address=primary_address,
            other_address=other_address,
        )

        mock_info = self.get_mock_info()
        mock_info["Henkilo"]["Turvakielto"]["TurvakieltoTieto"] = None
        mock_get_access_token.return_value = "test-access-token"
        mock_request_person_info.return_value = self.MockResponse(data=mock_info)
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}

        get_person_info(customer.national_id_number)
        customer.refresh_from_db()

        retained_fields = {
            "first_name": "Known First",
            "last_name": "Known Last",
            "phone_number": "0401234567",
            "primary_address_id": primary_address.id,
            "primary_address_apartment": "A1",
            "primary_address_apartment_sv": "A1 sv",
            "other_address_id": other_address.id,
            "other_address_apartment": "B2",
            "other_address_apartment_sv": "B2 sv",
            "source_system": SourceSystem.HELSINKI_PROFILE,
            "source_id": "known-source-id",
            "user_id": user.id,
            "national_id_number": "010199-1234",
            "email": "known@example.com",
            "address_security_ban": True,
            "driver_license_checked": True,
            "zone_id": zone.id,
            "language": Languages.SWEDISH,
            "is_anonymized": True,
        }
        for field_name, expected_value in retained_fields.items():
            with self.subTest(field=field_name):
                self.assertEqual(getattr(customer, field_name), expected_value)

    @patch("parking_permits.services.dvv.get_access_token")
    @patch("parking_permits.services.dvv._request_person_info")
    def test_security_ban_unknown_values_return_none_and_log_error(
        self, mock_request_person_info, mock_get_access_token
    ):
        unknown_values = [
            True,
            False,
            0,
            1,
            "0",
            "",
            [],
            {},
            "unknown",
        ]
        mock_get_access_token.return_value = "test-access-token"
        for value in unknown_values:
            with self.subTest(value=value):
                mock_info = self.get_mock_info()
                mock_info["Henkilo"]["Turvakielto"]["TurvakieltoTieto"] = value
                mock_request_person_info.return_value = self.MockResponse(
                    data=mock_info
                )

                with self.assertLogs("db", level="ERROR") as logs:
                    customer = get_person_info("12345")

                self.assertEqual(customer, None)
                self.assertEqual(
                    logs.output,
                    [
                        "ERROR:db:Unknown address security ban value for customer_id=unknown"
                    ],
                )

    def get_mock_info(self, **kwargs):
        return {
            "Henkilo": {
                "NykyinenSukunimi": {"Sukunimi": "Häkkinen"},
                "NykyisetEtunimet": {"Etunimet": "Heikki"},
                "VakinainenKotimainenLahiosoite": {
                    "LahiosoiteS": "Käsivoide 1 A6",
                    "PostitoimipaikkaS": "Helsinki",
                    "LahiosoiteR": "Handkrem 1 A6",
                    "PostitoimipaikkaR": "Helsingfors",
                    "Postinumero": "10001",
                },
                "TilapainenKotimainenLahiosoite": {
                    "LahiosoiteS": "Käsivoide 6 B7",
                    "PostitoimipaikkaS": "Helsinki",
                    "LahiosoiteR": "Handkrem 6 B7",
                    "PostitoimipaikkaR": "Helsingfors",
                    "Postinumero": "10001",
                },
                "Turvakielto": {
                    "TurvakieltoTieto": None,
                    "TurvakieltoPaattymispvm": None,
                },
            },
            **kwargs,
        }

    def get_mock_info_empty_addresses(self, **kwargs):
        return {
            "Henkilo": {
                "NykyinenSukunimi": {"Sukunimi": "Oksanen"},
                "NykyisetEtunimet": {"Etunimet": "Ossi"},
                "VakinainenKotimainenLahiosoite": {
                    "LahiosoiteS": "",
                    "PostitoimipaikkaS": "",
                    "LahiosoiteR": "",
                    "PostitoimipaikkaR": "",
                    "Postinumero": "",
                },
                "TilapainenKotimainenLahiosoite": {
                    "LahiosoiteS": "",
                    "PostitoimipaikkaS": "",
                    "LahiosoiteR": "",
                    "PostitoimipaikkaR": "",
                    "Postinumero": "",
                },
                "Turvakielto": {
                    "TurvakieltoTieto": None,
                    "TurvakieltoPaattymispvm": None,
                },
            },
            **kwargs,
        }


class ParseSecurityBanTestCase(TestCase):
    def _person_info(self, *, security_ban_value):
        return {"Turvakielto": {"TurvakieltoTieto": security_ban_value}}

    def test_known_value_literal_one_returns_true(self):
        result = _parse_security_ban(
            person_info=self._person_info(security_ban_value="1"), customer_id="1"
        )
        self.assertEqual(result, True)

    def test_known_value_none_returns_false(self):
        result = _parse_security_ban(
            person_info=self._person_info(security_ban_value=None), customer_id="1"
        )
        self.assertEqual(result, False)

    def test_unknown_values_raise_error(self):
        unknown_values = [
            True,
            False,
            0,
            1,
            "0",
            "",
            [],
            {},
            "unknown",
        ]
        for value in unknown_values:
            with self.subTest(value=value):
                with self.assertRaises(UnknownAddressSecurityBanValueError) as context:
                    _parse_security_ban(
                        person_info=self._person_info(security_ban_value=value),
                        customer_id="1",
                    )
                self.assertEqual(
                    str(context.exception),
                    "Unknown address security ban value for customer_id=1",
                )


class DvvServiceTestCase(TestCase):
    def setUp(self):
        self.primary_address = factory.SubFactory(AddressFactory)
        self.other_address = factory.SubFactory(AddressFactory)

    @patch("parking_permits.services.dvv.get_person_info")
    def test_get_both_addresses(self, mock_method):
        customer = CustomerFactory(
            primary_address=self.primary_address,
            other_address=self.other_address,
        )
        mock_method.return_value = self.get_customer_info(customer)
        primary_address, other_address = get_addresses(customer.national_id_number)
        mock_method.assert_called_once()
        self.assertEqual(
            primary_address["street_name"], customer.primary_address.street_name
        )
        self.assertEqual(
            primary_address["street_number"], customer.primary_address.street_number
        )
        self.assertEqual(primary_address["city"], customer.primary_address.city)
        self.assertEqual(
            primary_address["postal_code"], customer.primary_address.postal_code
        )
        self.assertEqual(
            other_address["street_name"], customer.other_address.street_name
        )
        self.assertEqual(
            other_address["street_number"], customer.other_address.street_number
        )
        self.assertEqual(other_address["city"], customer.other_address.city)
        self.assertEqual(
            other_address["postal_code"], customer.other_address.postal_code
        )

    @patch("parking_permits.services.dvv.get_person_info")
    def test_get_only_primary_address(self, mock_method):
        customer = CustomerFactory(
            primary_address=self.primary_address,
            other_address=None,
        )
        mock_method.return_value = self.get_customer_info(customer)
        primary_address, other_address = get_addresses(customer.national_id_number)
        mock_method.assert_called_once()
        self.assertEqual(
            primary_address["street_name"], customer.primary_address.street_name
        )
        self.assertEqual(
            primary_address["street_number"], customer.primary_address.street_number
        )
        self.assertEqual(primary_address["city"], customer.primary_address.city)
        self.assertEqual(
            primary_address["postal_code"], customer.primary_address.postal_code
        )
        self.assertEqual(other_address, None)

    @patch("parking_permits.services.dvv.get_person_info")
    def test_get_only_other_address(self, mock_method):
        customer = CustomerFactory(
            primary_address=None,
            other_address=self.other_address,
        )
        mock_method.return_value = self.get_customer_info(customer)
        primary_address, other_address = get_addresses(customer.national_id_number)
        mock_method.assert_called_once()
        self.assertEqual(primary_address, None)
        self.assertEqual(
            other_address["street_name"], customer.other_address.street_name
        )
        self.assertEqual(
            other_address["street_number"], customer.other_address.street_number
        )
        self.assertEqual(other_address["city"], customer.other_address.city)
        self.assertEqual(
            other_address["postal_code"], customer.other_address.postal_code
        )

    @patch("parking_permits.services.dvv.get_person_info")
    def test_get_zero_addresses(self, mock_method):
        customer = CustomerFactory(
            primary_address=None,
            other_address=None,
        )
        mock_method.return_value = self.get_customer_info(customer)
        primary_address, other_address = get_addresses(customer.national_id_number)
        mock_method.assert_called_once()
        self.assertEqual(primary_address, None)
        self.assertEqual(other_address, None)

    def test_is_same_address(self):
        address = {
            "street_name": "Kaivokatu",
            "street_number": "4",
            "apartment": "A8",
            "city": "Helsinki",
            "postal_code": "00100",
        }
        other_address = {
            "street_name": "Kaivokatu",
            "street_number": "4",
            "apartment": "A8",
            "city": "Helsinki",
            "postal_code": "00100",
        }
        self.assertTrue(is_same_address(address, other_address))

    def test_is_same_address_different_city(self):
        address = {
            "street_name": "Kaivokatu",
            "street_number": "4",
            "apartment": "A8",
            "city": "Helsinki",
            "postal_code": "00100",
        }
        other_address = {
            "street_name": "Kaivokatu",
            "street_number": "4",
            "apartment": "A8",
            "city": "Turku",
            "postal_code": "20100",
        }
        self.assertFalse(is_same_address(address, other_address))

    def test_is_same_address_different_street_name(self):
        address = {
            "street_name": "Kaivokatu",
            "street_number": "4",
            "apartment": "A8",
            "city": "Helsinki",
            "postal_code": "00100",
        }
        other_address = {
            "street_name": "Mannerheimintie",
            "street_number": "4",
            "apartment": "A8",
            "city": "Helsinki",
            "postal_code": "00100",
        }
        self.assertFalse(is_same_address(address, other_address))

    def test_is_same_address_different_street_number(self):
        address = {
            "street_name": "Kaivokatu",
            "street_number": "4",
            "apartment": "A8",
            "city": "Helsinki",
            "postal_code": "00100",
        }
        other_address = {
            "street_name": "Kaivokatu",
            "street_number": "6",
            "apartment": "A8",
            "city": "Helsinki",
            "postal_code": "00100",
        }
        self.assertFalse(is_same_address(address, other_address))

    def test_is_same_address_different_postal_code(self):
        address = {
            "street_name": "Kaivokatu",
            "street_number": "4",
            "apartment": "A8",
            "city": "Helsinki",
            "postal_code": "00100",
        }
        other_address = {
            "street_name": "Kaivokatu",
            "street_number": "4",
            "apartment": "A8",
            "city": "Helsinki",
            "postal_code": "20100",
        }
        self.assertFalse(is_same_address(address, other_address))

    def test_is_same_address_different_apartment(self):
        address = {
            "street_name": "Kaivokatu",
            "street_number": "4",
            "apartment": "A8",
            "city": "Helsinki",
            "postal_code": "00100",
        }
        other_address = {
            "street_name": "Kaivokatu",
            "street_number": "4",
            "apartment": "A7",
            "city": "Helsinki",
            "postal_code": "00100",
        }
        self.assertFalse(is_same_address(address, other_address))

    @staticmethod
    def get_customer_info(customer):
        return {
            "national_id_number": customer.national_id_number,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "primary_address": to_dict(customer.primary_address),
            "other_address": to_dict(customer.other_address),
            "phone_number": "",
            "email": "",
            "address_security_ban": False,
            "driver_license_checked": False,
        }
