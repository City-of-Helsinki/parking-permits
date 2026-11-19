from django.conf import settings
from django.contrib.gis.geos import Point
from django.test import TestCase

from parking_permits.tests.factories.address import AddressFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory


class AddressSwedishFormatTestCase(TestCase):
    def setUp(self):
        self.address = AddressFactory(
            street_name="Mannerheimintie",
            street_name_sv="Mannerheimvägen",
            street_number="1",
            city="HELSINKI",
            city_sv="HELSINGFORS",
            postal_code="00100",
        )
        self.address_without_sv = AddressFactory(
            street_name="Mannerheimintie",
            street_name_sv="",
            street_number="2",
            city="HELSINKI",
            city_sv="",
            postal_code="00100",
        )

    def test_format_sv_uses_swedish_names(self):
        self.assertEqual(
            self.address.format_sv("A 6"), "Mannerheimvägen 1 A 6, 00100 HELSINGFORS"
        )

    def test_format_sv_falls_back_to_finnish_names(self):
        self.assertEqual(
            self.address_without_sv.format_sv("A 6"),
            "Mannerheimintie 2 A 6, 00100 HELSINKI",
        )

    def test_format_sv_falls_back_to_finnish_apartment(self):
        self.assertEqual(
            self.address.format_sv("", "A 6"),
            "Mannerheimvägen 1 A 6, 00100 HELSINGFORS",
        )

    def test_format_sv_without_apartment_does_not_print_none(self):
        self.assertNotIn("None", self.address.format_sv(None, None))

    def test_permit_full_address_sv(self):
        permit = ParkingPermitFactory(
            address=self.address_without_sv, address_apartment_sv="A 6"
        )
        self.assertEqual(
            permit.full_address_sv, "Mannerheimintie 2 A 6, 00100 HELSINKI"
        )

    def test_permit_full_address_sv_without_address(self):
        permit = ParkingPermitFactory(address=None)
        self.assertEqual(permit.full_address_sv, "")

    def test_permit_full_next_address_sv(self):
        permit = ParkingPermitFactory(
            next_address=self.address_without_sv, next_address_apartment_sv="A 6"
        )
        self.assertEqual(
            permit.full_next_address_sv, "Mannerheimintie 2 A 6, 00100 HELSINKI"
        )

    def test_permit_full_next_address_sv_without_address(self):
        permit = ParkingPermitFactory(next_address=None)
        self.assertEqual(permit.full_next_address_sv, "")

    def test_customer_full_primary_address_sv(self):
        customer = CustomerFactory(
            primary_address=self.address_without_sv,
            primary_address_apartment_sv="A 6",
        )
        self.assertEqual(
            customer.full_primary_address_sv, "Mannerheimintie 2 A 6, 00100 HELSINKI"
        )

    def test_customer_full_other_address_sv(self):
        customer = CustomerFactory(
            other_address=self.address_without_sv, other_address_apartment_sv="A 6"
        )
        self.assertEqual(
            customer.full_other_address_sv, "Mannerheimintie 2 A 6, 00100 HELSINKI"
        )

    def test_customer_full_addresses_sv_without_addresses(self):
        customer = CustomerFactory(primary_address=None, other_address=None)
        self.assertEqual(customer.full_primary_address_sv, "")
        self.assertEqual(customer.full_other_address_sv, "")


class AddressStrRepresentationTestCase(TestCase):
    def test_string_representation_intentionally_includes_street_details(
        self,
    ):
        """Unlike Customer.__str__, Address.__str__ intentionally
        keeps the street name/number and city.

        It is rendered directly in permit and temporary-vehicle e-mail
        templates so customers can see their own address, so do not
        strip it here without also updating those customer-facing
        usages.
        """
        address = AddressFactory(
            street_name="Testikatu", street_number="1", city="Helsinki"
        )

        self.assertIn("Testikatu", str(address))
        self.assertIn("Helsinki", str(address))


class AddressZoneTestCase(TestCase):
    def test_zone_lookup_failure_logs_address_id_instead_of_address(self):
        address = AddressFactory(
            street_name="Testikatu", street_number="1", city="Helsinki"
        )
        # Move the address far away from any known parking zone so that
        # the zone lookup fails with ParkingZone.DoesNotExist.
        address.location = Point(0.0, 0.0, srid=settings.SRID)
        address.save()

        with self.assertLogs("db", level="WARNING") as logs:
            zone = address.zone

        self.assertIsNone(zone)
        log_output = "\n".join(logs.output)
        self.assertIn(f"address_id={address.pk}", log_output)
        self.assertNotIn("Testikatu", log_output)
        self.assertNotIn("Helsinki", log_output)
