import random
import string

import factory

from parking_permits_app.models import Customer
from parking_permits_app.tests.factories.address import AddressFactory


def generate_random_national_id():
    birthday = "".join(random.choices(string.digits, k=6))
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{birthday}-{suffix}"


class CustomerFactory(factory.django.DjangoModelFactory):
    id = factory.Faker("uuid4")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    national_id_number = factory.LazyFunction(generate_random_national_id)
    primary_address = factory.SubFactory(AddressFactory)
    other_address = factory.SubFactory(AddressFactory)

    class Meta:
        model = Customer
