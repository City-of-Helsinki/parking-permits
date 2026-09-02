from django.conf import settings
from django.contrib.gis.geos import Point
from django.test import TestCase

from parking_permits.tests.factories.address import AddressFactory


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
