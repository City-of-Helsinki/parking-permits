from unittest.mock import patch

import factory
from django.test import TestCase

from parking_permits.services.dvv import get_addresses, get_person_info
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
        mock_info["Henkilo"]["VakinainenKotimainenLahiosoite"][
            "LahiosoiteS"
        ] = "Käsivoide 1"
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
        mock_info["Henkilo"]["VakinainenKotimainenLahiosoite"][
            "PostitoimipaikkaS"
        ] = "Vantaa"
        mock_info["Henkilo"]["TilapainenKotimainenLahiosoite"][
            "PostitoimipaikkaS"
        ] = "Espoo"
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
        mock_info["Henkilo"]["VakinainenKotimainenLahiosoite"]["LahiosoiteR"] = None

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
            },
            **kwargs,
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
        mock_method.return_value = self.get_customer_mapping(customer)
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
        mock_method.return_value = self.get_customer_mapping(customer)
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
        mock_method.return_value = self.get_customer_mapping(customer)
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
        mock_method.return_value = self.get_customer_mapping(customer)
        primary_address, other_address = get_addresses(customer.national_id_number)
        mock_method.assert_called_once()
        self.assertEqual(primary_address, None)
        self.assertEqual(other_address, None)

    @staticmethod
    def get_customer_mapping(customer):
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
