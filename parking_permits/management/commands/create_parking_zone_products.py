import logging
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from parking_permits.models import ParkingZone, Product
from parking_permits.models.product import ProductType

logger = logging.getLogger("db")

ZONE_MONTHLY_PRICES = {
    "A": Decimal("30.00"),
    "B": Decimal("30.00"),
    "C": Decimal("30.00"),
    "D": Decimal("30.00"),
    "E": Decimal("30.00"),
    "F": Decimal("30.00"),
    "H": Decimal("30.00"),
    "I": Decimal("30.00"),
    "J": Decimal("30.00"),
    "K": Decimal("30.00"),
    "L": Decimal("30.00"),
    "M": Decimal("15.00"),
    "N": Decimal("15.00"),
    "O": Decimal("15.00"),
    "P": Decimal("15.00"),
}


class Command(BaseCommand):
    help = "Create test resident products for parking zones"

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=datetime.now().year)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stdout.write("Cannot create test data in production environment")
            return

        start_date = date(options["year"], 1, 1)
        end_date = date(options["year"], 12, 31)
        for zone_name, zone_price in ZONE_MONTHLY_PRICES.items():
            zone = ParkingZone.objects.get(name=zone_name)
            product = Product.objects.get_or_create(
                zone=zone,
                start_date=start_date,
                end_date=end_date,
                defaults={
                    "type": ProductType.RESIDENT,
                    "unit_price": zone_price,
                    "vat": Decimal(0.24),
                    "low_emission_discount": Decimal(0.5),
                },
            )
            if not product[0].talpa_product_id:
                product[0].create_talpa_product()

        self.stdout.write("Test resident products created")
