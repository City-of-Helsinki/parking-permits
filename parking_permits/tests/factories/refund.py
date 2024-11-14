from decimal import Decimal

import factory

from parking_permits.models import Refund


class RefundFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")
    amount = Decimal(50)
    iban = "FI5399965432932146"

    class Meta:
        model = Refund

    @factory.post_generation
    def orders(self, create, extracted, **kwargs):
        if not create or not extracted:
            return
        self.orders.add(*extracted)
