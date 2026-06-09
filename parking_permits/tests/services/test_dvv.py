from unittest.mock import patch

import factory
from django.test import TestCase

from parking_permits.exceptions import ObjectNotFoundError
from parking_permits.services.dvv import (
    DATA_GROUP_ADDRESS_SECURITY_BAN,
    DATA_GROUP_PERMANENT_ADDRESS,
    DATA_GROUP_PERSON_NAME,
    DATA_GROUP_TEMPORARY_ADDRESS,
    DEFAULT_REQUEST_DATA_GROUPS,
    _build_apartment_string,
    format_address,
    get_addresses,
    get_person_data_by_data_groups,
    get_person_info,
    get_request_data,
    is_same_address,
    is_valid_address,
)
from parking_permits.tests.factories.customer import AddressFactory, CustomerFactory
from parking_permits.tests.factories.zone import generate_multi_polygon
from parking_permits.utils import to_dict


class GetPersonInfoTestCase(TestCase):
    class MockResponse:
        def __init__(self, *, data=None, ok=True, text=""):
            self.data = data
            self.ok = ok
            self.text = text

        def json(self):
            return self.data

    def get_data_group(self, mock_info, group_name):
        """Helper to find a data group by name in the new DVV response format."""
        for group in mock_info["perustiedot"][0]["tietoryhmat"]:
            if group.get("tietoryhma") == group_name:
                return group
        raise ValueError(f"Data group {group_name} not found in mock info")

    @patch("requests.post")
    def test_bad_response(self, mock_post):
        mock_post.return_value = self.MockResponse(ok=False, text="oops")
        customer = get_person_info("12345")
        self.assertEqual(customer, None)

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("requests.post")
    def test_get_customer_info(self, mock_post, mock_get_address_details):
        mock_post.return_value = self.MockResponse(data=self.get_mock_info())
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
    @patch("requests.post")
    def test_get_customer_info_apartment_not_included(
        self, mock_post, mock_get_address_details
    ):
        mock_info = self.get_mock_info()
        permanent_address = self.get_data_group(mock_info, DATA_GROUP_PERMANENT_ADDRESS)
        permanent_address["huoneistokirjain"] = ""
        permanent_address["huoneistonumero"] = ""

        mock_post.return_value = self.MockResponse(data=mock_info)
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
    @patch("requests.post")
    def test_get_customer_info_addresses_not_in_helsinki(
        self, mock_post, mock_get_address_details
    ):
        mock_info = self.get_mock_info()
        permanent_address = self.get_data_group(mock_info, DATA_GROUP_PERMANENT_ADDRESS)
        permanent_address["postitoimipaikka"]["fi"] = "Vantaa"
        temporary_address = self.get_data_group(mock_info, DATA_GROUP_TEMPORARY_ADDRESS)
        temporary_address["postitoimipaikka"]["fi"] = "Espoo"

        mock_post.return_value = self.MockResponse(data=mock_info)
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}

        customer = get_person_info("12345")
        self.assertEqual(customer["first_name"], "Heikki")
        self.assertEqual(customer["last_name"], "Häkkinen")
        self.assertEqual(customer["primary_address"], None)
        self.assertEqual(customer["primary_address_apartment"], "")
        self.assertEqual(customer["other_address"], None)
        self.assertEqual(customer["other_address_apartment"], "")

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("requests.post")
    def test_mock_customer_info_null_swedish_address(
        self, mock_post, mock_get_address_details
    ):
        mock_info = self.get_mock_info()
        permanent_address = self.get_data_group(mock_info, DATA_GROUP_PERMANENT_ADDRESS)
        permanent_address["katunimi"]["sv"] = None

        mock_post.return_value = self.MockResponse(data=mock_info)
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

    @patch("requests.post")
    def test_get_person_info_returns_none_on_empty_response(self, mock_post):
        """DVV response missing 'perustiedot' key should return None."""
        mock_post.return_value = self.MockResponse(data={"ajanTasalla": True})

        result = get_person_info("12345")
        self.assertIsNone(result)

    @patch("requests.post")
    def test_get_person_info_returns_none_on_zero_matches(self, mock_post):
        """DVV response with empty 'perustiedot' list should return None."""
        mock_post.return_value = self.MockResponse(
            data={"ajanTasalla": True, "perustiedot": []}
        )

        result = get_person_info("12345")
        self.assertIsNone(result)

    def test_get_person_data_by_data_groups_parses_correctly(self):
        """Should parse data groups from DVV response into a dict keyed by group name."""
        response_data = self.get_mock_info()

        result = get_person_data_by_data_groups(response_data)

        self.assertIn(DATA_GROUP_PERSON_NAME, result)
        self.assertIn(DATA_GROUP_PERMANENT_ADDRESS, result)
        self.assertIn(DATA_GROUP_TEMPORARY_ADDRESS, result)
        self.assertIn(DATA_GROUP_ADDRESS_SECURITY_BAN, result)

        # Verify 'tietoryhma' key is removed from each group
        self.assertNotIn("tietoryhma", result[DATA_GROUP_PERSON_NAME])
        self.assertNotIn("tietoryhma", result[DATA_GROUP_PERMANENT_ADDRESS])
        self.assertNotIn("tietoryhma", result[DATA_GROUP_TEMPORARY_ADDRESS])
        self.assertNotIn("tietoryhma", result[DATA_GROUP_ADDRESS_SECURITY_BAN])

        # Verify each data group matches the original (minus 'tietoryhma' key)
        for original_group in response_data["perustiedot"][0]["tietoryhmat"]:
            group_name = original_group["tietoryhma"]
            expected_data = {
                key: value
                for key, value in original_group.items()
                if key != "tietoryhma"
            }
            self.assertEqual(result[group_name], expected_data)

    def test_get_person_data_by_data_groups_raises_on_multiple_persons(self):
        """Should raise ValueError when multiple persons in response and force_single_person=True."""
        response_data = {
            "perustiedot": [
                {"henkilotunnus": "12345", "tietoryhmat": []},
                {"henkilotunnus": "67890", "tietoryhmat": []},
            ]
        }

        with self.assertRaises(ValueError) as context:
            get_person_data_by_data_groups(response_data, force_single_person=True)

        self.assertEqual(
            str(context.exception), "Expected exactly one person info in DVV response"
        )

    def test_get_person_data_by_data_groups_returns_none_on_no_persons(self):
        """Should return None when no persons in response."""
        response_data = {"perustiedot": []}
        result = get_person_data_by_data_groups(response_data)
        self.assertIsNone(result)

    def test_get_person_data_by_data_groups_returns_none_on_no_data(self):
        """Should return None when 'perustiedot' key is missing."""
        response_data = {}
        result = get_person_data_by_data_groups(response_data)
        self.assertIsNone(result)

    def test_build_apartment_string_full_apartment(self):
        """Should combine letter, number, and suffix correctly."""
        address_data = {
            "huoneistokirjain": "A",
            "huoneistonumero": "006",
            "jakokirjain": "b",
        }
        result = _build_apartment_string(address_data)
        self.assertEqual(result, "A6b")

    def test_build_apartment_string_letter_and_number_only(self):
        """Should handle apartment with letter and number, no suffix."""
        address_data = {
            "huoneistokirjain": "B",
            "huoneistonumero": "012",
        }
        result = _build_apartment_string(address_data)
        self.assertEqual(result, "B12")

    def test_build_apartment_string_number_only(self):
        """Should handle apartment with number only."""
        address_data = {
            "huoneistokirjain": "",
            "huoneistonumero": "007",
        }
        result = _build_apartment_string(address_data)
        self.assertEqual(result, "7")

    def test_build_apartment_string_empty_fields(self):
        """Should return empty string when no apartment data."""
        address_data = {
            "huoneistokirjain": "",
            "huoneistonumero": "",
        }
        result = _build_apartment_string(address_data)
        self.assertEqual(result, "")

    def test_build_apartment_string_zero_apartment_number(self):
        """Should treat '000' as no apartment number."""
        address_data = {
            "huoneistokirjain": "A",
            "huoneistonumero": "000",
        }
        result = _build_apartment_string(address_data)
        self.assertEqual(result, "A")

    def test_build_apartment_string_suffix_only(self):
        """Should handle apartment with only a division letter (jakokirjain)."""
        address_data = {"jakokirjain": "b"}
        result = _build_apartment_string(address_data)
        self.assertEqual(result, "b")

    def test_build_apartment_string_empty_dict(self):
        """Should return empty string when no apartment keys are present."""
        result = _build_apartment_string({})
        self.assertEqual(result, "")

    def test_build_apartment_string_strips_leading_zeros(self):
        """Should strip leading zeros from the apartment number."""
        address_data = {
            "huoneistokirjain": "A",
            "huoneistonumero": "001",
        }
        result = _build_apartment_string(address_data)
        self.assertEqual(result, "A1")

    @patch("parking_permits.services.dvv.get_address_details")
    def test_format_address_capitalizes_city(self, mock_get_address_details):
        """DVV returns city names in uppercase, which should be capitalized."""
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}
        address_data = self.get_data_group(
            self.get_mock_info(), DATA_GROUP_PERMANENT_ADDRESS
        )

        address = format_address(address_data)

        self.assertEqual(address["city"], "Helsinki")
        self.assertEqual(address["city_sv"], "Helsingfors")

    @patch("parking_permits.services.dvv.get_address_details")
    def test_format_address_apartment_sv_equals_apartment(
        self, mock_get_address_details
    ):
        """New DVV-API does not separate finnish and swedish apartment data."""
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}
        address_data = self.get_data_group(
            self.get_mock_info(), DATA_GROUP_PERMANENT_ADDRESS
        )

        address = format_address(address_data)

        self.assertEqual(address["apartment"], "A6")
        self.assertEqual(address["apartment_sv"], address["apartment"])

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("requests.post")
    def test_get_person_info_security_ban_active(
        self, mock_post, mock_get_address_details
    ):
        """An active address security ban should be reflected in the result."""
        mock_info = self.get_mock_info()
        security_ban = self.get_data_group(mock_info, DATA_GROUP_ADDRESS_SECURITY_BAN)
        # modify dict by reference to set the security ban as active
        security_ban["turvakieltoAktiivinen"] = True

        mock_post.return_value = self.MockResponse(data=mock_info)
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}

        customer = get_person_info("12345")
        self.assertTrue(customer["address_security_ban"])

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("requests.post")
    def test_get_person_info_security_ban_missing_group(
        self, mock_post, mock_get_address_details
    ):
        """A missing security ban data group should default to False."""
        mock_info = self.get_mock_info()
        data_groups = mock_info["perustiedot"][0]["tietoryhmat"]
        # remove the address security ban group from the response to simulate it being missing
        mock_info["perustiedot"][0]["tietoryhmat"] = [
            group
            for group in data_groups
            if group.get("tietoryhma") != DATA_GROUP_ADDRESS_SECURITY_BAN
        ]

        mock_post.return_value = self.MockResponse(data=mock_info)
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}

        customer = get_person_info("12345")
        self.assertFalse(customer["address_security_ban"])

    @patch("parking_permits.services.dvv.get_address_details")
    @patch("requests.post")
    def test_get_person_info_missing_name_group(
        self, mock_post, mock_get_address_details
    ):
        """A missing person name data group should default names to empty strings."""
        mock_info = self.get_mock_info()
        data_groups = mock_info["perustiedot"][0]["tietoryhmat"]
        # remove the person name group from the response to simulate it being missing
        mock_info["perustiedot"][0]["tietoryhmat"] = [
            group
            for group in data_groups
            if group.get("tietoryhma") != DATA_GROUP_PERSON_NAME
        ]

        mock_post.return_value = self.MockResponse(data=mock_info)
        mock_get_address_details.return_value = {"location": generate_multi_polygon()}

        customer = get_person_info("12345")
        self.assertEqual(customer["first_name"], "")
        self.assertEqual(customer["last_name"], "")

    def test_get_person_data_by_data_groups_multiple_persons(self):
        """With force_single_person=False, should return a list with one entry per person."""
        response_data = {
            "perustiedot": [
                {
                    "henkilotunnus": "12345",
                    "tietoryhmat": [
                        {
                            "etunimi": "Heikki",
                            "sukunimi": "Häkkinen",
                            "tietoryhma": DATA_GROUP_PERSON_NAME,
                        },
                    ],
                },
                {
                    "henkilotunnus": "67890",
                    "tietoryhmat": [
                        {
                            "etunimi": "Maija",
                            "sukunimi": "Meikäläinen",
                            "tietoryhma": DATA_GROUP_PERSON_NAME,
                        },
                    ],
                },
            ]
        }

        result = get_person_data_by_data_groups(
            response_data, force_single_person=False
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][DATA_GROUP_PERSON_NAME]["etunimi"], "Heikki")
        self.assertEqual(result[1][DATA_GROUP_PERSON_NAME]["etunimi"], "Maija")

    def test_get_person_data_by_data_groups_partial_groups(self):
        """Should parse a response that includes only a subset of the data groups."""
        response_data = {
            "perustiedot": [
                {
                    "henkilotunnus": "12345",
                    "tietoryhmat": [
                        {
                            "etunimi": "Heikki",
                            "sukunimi": "Häkkinen",
                            "tietoryhma": DATA_GROUP_PERSON_NAME,
                        },
                    ],
                }
            ]
        }

        result = get_person_data_by_data_groups(response_data)

        self.assertIn(DATA_GROUP_PERSON_NAME, result)
        self.assertNotIn(DATA_GROUP_PERMANENT_ADDRESS, result)
        self.assertNotIn(DATA_GROUP_TEMPORARY_ADDRESS, result)
        self.assertNotIn(DATA_GROUP_ADDRESS_SECURITY_BAN, result)

    def get_mock_info(self, **kwargs):
        return {
            "ajanTasalla": True,
            "perustiedot": [
                {
                    "henkilotunnus": "12345",
                    "tietoryhmat": [
                        {
                            "alkupv": {"arvo": "2019-05-08", "tarkkuus": "PAIVA"},
                            "etunimi": "Heikki",
                            "etunimiUTF8": "Heikki",
                            "sukunimi": "Häkkinen",
                            "sukunimiUTF8": "Häkkinen",
                            "tietoryhma": DATA_GROUP_PERSON_NAME,
                        },
                        {
                            "alkupv": {"arvo": "1986-06-02", "tarkkuus": "PAIVA"},
                            "huoneistokirjain": "A",
                            "huoneistonumero": "006",
                            "katunimi": {"fi": "Käsivoide", "sv": "Handkrem"},
                            "katunumero": "1",
                            "kuntakoodi": "091",
                            "osoitenumero": 1,
                            "postinumero": "10001",
                            "postitoimipaikka": {"fi": "HELSINKI", "sv": "HELSINGFORS"},
                            "rakennustunnus": "",
                            "tietoryhma": DATA_GROUP_PERMANENT_ADDRESS,
                        },
                        {
                            "alkupv": {"arvo": "1986-06-02", "tarkkuus": "PAIVA"},
                            "huoneistokirjain": "B",
                            "huoneistonumero": "007",
                            "huoneistokirjain_sv": "B",
                            "huoneistonumero_sv": "007",
                            "katunimi": {"fi": "Käsivoide", "sv": "Handkrem"},
                            "katunumero": "6",
                            "kuntakoodi": "091",
                            "osoitenumero": 1,
                            "postinumero": "10001",
                            "postitoimipaikka": {"fi": "HELSINKI", "sv": "HELSINGFORS"},
                            "rakennustunnus": "",
                            "tietoryhma": DATA_GROUP_TEMPORARY_ADDRESS,
                        },
                        {
                            "turvakieltoAktiivinen": False,
                            "tietoryhma": DATA_GROUP_ADDRESS_SECURITY_BAN,
                        },
                    ],
                    **kwargs,
                }
            ],
        }


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

    @patch("parking_permits.services.dvv.get_person_info")
    def test_get_addresses_empty_national_id(self, mock_method):
        """An empty national id should return no addresses without querying DVV."""
        primary_address, other_address = get_addresses("")
        mock_method.assert_not_called()
        self.assertEqual(primary_address, None)
        self.assertEqual(other_address, None)

    @patch("parking_permits.services.dvv.get_person_info")
    def test_get_addresses_raises_when_person_not_found(self, mock_method):
        """A missing person should raise ObjectNotFoundError."""
        mock_method.return_value = None
        with self.assertRaises(ObjectNotFoundError):
            get_addresses("12345")
        mock_method.assert_called_once()

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


class GetRequestDataTestCase(TestCase):
    def test_get_request_data_wraps_single_id_in_list(self):
        """A single national id should be wrapped in a list under 'hetulista'."""
        data = get_request_data("12345")
        self.assertEqual(data["hetulista"], ["12345"])

    def test_get_request_data_keeps_list_of_ids(self):
        """A list of national ids should be preserved as-is."""
        data = get_request_data(["12345", "67890"])
        self.assertEqual(data["hetulista"], ["12345", "67890"])

    def test_get_request_data_uses_default_data_groups(self):
        """Without explicit data groups, the default groups should be used."""
        data = get_request_data("12345")
        self.assertEqual(data["tietoryhmat"], DEFAULT_REQUEST_DATA_GROUPS)

    def test_get_request_data_uses_custom_data_groups(self):
        """Custom data groups should be passed through unchanged."""
        custom_groups = [DATA_GROUP_PERSON_NAME]
        data = get_request_data("12345", data_groups=custom_groups)
        self.assertEqual(data["tietoryhmat"], custom_groups)


class IsValidAddressTestCase(TestCase):
    @staticmethod
    def build_address(*, city="HELSINKI", street_name="Käsivoide"):
        return {
            "katunimi": {"fi": street_name, "sv": "Handkrem"},
            "postitoimipaikka": {"fi": city, "sv": "HELSINGFORS"},
        }

    def test_is_valid_address_valid_helsinki(self):
        self.assertTrue(is_valid_address(self.build_address()))

    def test_is_valid_address_not_in_helsinki(self):
        self.assertFalse(is_valid_address(self.build_address(city="Vantaa")))

    def test_is_valid_address_missing_street_name(self):
        address = self.build_address()
        address["katunimi"]["fi"] = None
        self.assertFalse(is_valid_address(address))

    def test_is_valid_address_missing_city(self):
        address = self.build_address()
        address["postitoimipaikka"]["fi"] = None
        self.assertFalse(is_valid_address(address))

    def test_is_valid_address_none(self):
        self.assertFalse(is_valid_address(None))
