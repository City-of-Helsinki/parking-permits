from unittest.mock import patch

import factory
from django.test import TestCase

from parking_permits.services.dvv import get_addresses
from parking_permits.tests.factories.customer import AddressFactory, CustomerFactory
from parking_permits.utils import to_dict


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
