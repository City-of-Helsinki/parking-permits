import random
import string

import factory
import pytz

from parking_permits.models import Vehicle
from parking_permits.models.vehicle import LowEmissionCriteria, VehiclePowerType
from parking_permits.tests.factories.faker import fake


def generate_random_registration_number():
    part_1 = "".join(random.choices(string.ascii_uppercase, k=3))
    part_2 = "".join(random.choices(string.digits, k=3))
    return f"{part_1}-{part_2}"


class VehiclePowerTypeFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("name")
    identifier = factory.Faker("random_int", min=0, max=100)

    class Meta:
        model = VehiclePowerType


class VehicleFactory(factory.django.DjangoModelFactory):
    manufacturer = factory.Faker("name")
    model = factory.Faker("name")
    registration_number = factory.LazyFunction(generate_random_registration_number)
    emission = random.randint(0, 90)
    last_inspection_date = factory.Faker("date")
    power_type = factory.SubFactory(VehiclePowerTypeFactory)

    class Meta:
        model = Vehicle


class LowEmissionCriteriaFactory(factory.django.DjangoModelFactory):
    nedc_max_emission_limit = fake.random.randint(1, 50)
    wltp_max_emission_limit = fake.random.randint(50, 150)
    euro_min_class_limit = fake.random.randint(1, 6)
    start_date = factory.LazyFunction(
        lambda: fake.date_time_between(
            start_date="-2h", end_date="-1h", tzinfo=pytz.utc
        )
    )
    end_date = factory.LazyFunction(
        lambda: fake.date_time_between(
            start_date="+1h", end_date="+2h", tzinfo=pytz.utc
        )
    )

    class Meta:
        model = LowEmissionCriteria
