from decimal import Decimal

import factory

from parking_permits.models import Refund
from parking_permits.tests.factories.order import OrderFactory


class RefundFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")
    order = factory.SubFactory(OrderFactory)
    amount = Decimal(50)
    iban = "FI10000000000001111"

    class Meta:
        model = Refund
