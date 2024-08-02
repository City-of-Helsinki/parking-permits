import logging
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from parking_permits.models import ParkingZone, Product
from parking_permits.models.product import ProductType

logger = logging.getLogger("db")

OLD_ZONE_MONTHLY_PRICES = {
    "A": Decimal("30.00"),
    "B": Decimal("30.00"),
    "C": Decimal("30.00"),
    "D": Decimal("30.00"),
    "DC": Decimal("30.00"),
    "E": Decimal("30.00"),
    "F": Decimal("30.00"),
    "H": Decimal("30.00"),
    "I": Decimal("30.00"),
    "J": Decimal("30.00"),
    "K": Decimal("30.00"),
    "L": Decimal("30.00"),
}

NEW_ZONE_MONTHLY_PRICES = {
    "M": Decimal("15.00"),
    "N": Decimal("15.00"),
    "O": Decimal("15.00"),
    "P": Decimal("15.00"),
}


class Command(BaseCommand):
    help = "Create test resident products for parking zones"

    def add_arguments(self, parser):
        parser.add_argument(
            "--start_date", type=str, default="%s-01-01" % datetime.now().year
        )
        parser.add_argument(
            "--end_date", type=str, default="%s-12-31" % datetime.now().year
        )
        parser.add_argument(
            "--price_increment_factor_old_zone", type=float, default=1.0
        )
        parser.add_argument(
            "--price_increment_factor_new_zone", type=float, default=1.0
        )
        parser.add_argument("--low_emission_discount_old_zone", type=float, default=0.5)
        parser.add_argument("--low_emission_discount_new_zone", type=float, default=0.5)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stdout.write("Cannot create test data in production environment")
            return

        start_date = datetime.strptime(options["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(options["end_date"], "%Y-%m-%d").date()
        for zone_name, zone_price in OLD_ZONE_MONTHLY_PRICES.items():
            zone = ParkingZone.objects.get(name=zone_name)
            product = Product.objects.get_or_create(
                zone=zone,
                start_date=start_date,
                end_date=end_date,
                defaults={
                    "type": ProductType.RESIDENT,
                    "unit_price": zone_price
                    * Decimal(options["price_increment_factor_old_zone"]),
                    "vat": Decimal(0.255),
                    "low_emission_discount": Decimal(
                        options["low_emission_discount_old_zone"]
                    ),
                },
            )
            if not product[0].talpa_product_id:
                product[0].create_talpa_product()

        for zone_name, zone_price in NEW_ZONE_MONTHLY_PRICES.items():
            zone = ParkingZone.objects.get(name=zone_name)
            product = Product.objects.get_or_create(
                zone=zone,
                start_date=start_date,
                end_date=end_date,
                defaults={
                    "type": ProductType.RESIDENT,
                    "unit_price": zone_price
                    * Decimal(options["price_increment_factor_new_zone"]),
                    "vat": Decimal(0.255),
                    "low_emission_discount": Decimal(
                        options["low_emission_discount_new_zone"]
                    ),
                },
            )
            if not product[0].talpa_product_id:
                product[0].create_talpa_product()

        self.stdout.write("Test resident products created")
