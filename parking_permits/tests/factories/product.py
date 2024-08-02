from datetime import date
from decimal import Decimal

import factory

from parking_permits.models import Product

from .zone import ParkingZoneFactory


class ProductFactory(factory.django.DjangoModelFactory):
    zone = factory.SubFactory(ParkingZoneFactory)
    start_date = date(2021, 1, 1)
    end_date = date(2021, 12, 31)
    unit_price = Decimal(30)
    vat = Decimal(0.255)
    low_emission_discount = Decimal(0.5)

    class Meta:
        model = Product
