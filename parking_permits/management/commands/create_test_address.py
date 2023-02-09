import logging

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import transaction

from parking_permits.models import Address, ParkingZone

logger = logging.getLogger("db")
addresses = [
    {
        "street_name": "Käsivoide",
        "street_name_sv": "Handcream",
        "street_number": "1/2 A 1k",
        "city": "Helsinki",
        "city_sv": "Helsingfors",
        "postal_code": "00580",
        "location": Point([24.95587348590678, 60.17392205331229], srid=settings.SRID),
    },
    {
        "street_name": "Tarkk'ampujankatu",
        "street_name_sv": "Skarpskyttegatan",
        "street_number": "80 A 3a",
        "city": "Helsinki",
        "city_sv": "Helsingfors",
        "postal_code": "00130",
        "location": Point([24.942483898504985, 60.16075503675933], srid=settings.SRID),
    },
]


class Command(BaseCommand):
    help = "Create test secondary address for test user"

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stdout.write("Cannot create test address in production environment")
            return
        for address in addresses:
            Address.objects.update_or_create(
                street_name=address["street_name"],
                street_number=address["street_number"],
                city=address["city"],
                _zone=ParkingZone.objects.get_for_location(address["location"]),
                defaults=address,
            )

        self.stdout.write("Test address created")
