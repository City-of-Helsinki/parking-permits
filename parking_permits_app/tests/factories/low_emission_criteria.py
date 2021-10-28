import factory
import pytz

from parking_permits_app.models import LowEmissionCriteria
from parking_permits_app.tests.factories.faker import fake
from parking_permits_app.tests.factories.vehicle import VehicleTypeFactory


class LowEmissionCriteriaFactory(factory.django.DjangoModelFactory):
    vehicle_type = factory.SubFactory(VehicleTypeFactory)
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
