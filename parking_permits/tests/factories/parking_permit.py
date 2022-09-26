import factory

from parking_permits.models import ParkingPermit
from parking_permits.tests.factories import ParkingZoneFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.vehicle import VehicleFactory


class ParkingPermitFactory(factory.django.DjangoModelFactory):
    customer = factory.SubFactory(CustomerFactory)
    vehicle = factory.SubFactory(VehicleFactory)
    parking_zone = factory.SubFactory(ParkingZoneFactory)

    class Meta:
        model = ParkingPermit

    @factory.post_generation
    def orders(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for order in extracted:
                self.orders.add(order)
