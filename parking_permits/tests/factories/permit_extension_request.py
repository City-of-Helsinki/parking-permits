import factory

from parking_permits.models import ParkingPermitExtensionRequest
from parking_permits.tests.factories.order import OrderFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory


class ParkingPermitExtensionRequestFactory(factory.django.DjangoModelFactory):
    permit = factory.SubFactory(ParkingPermitFactory)
    order = factory.SubFactory(OrderFactory)
    month_count = 1

    class Meta:
        model = ParkingPermitExtensionRequest
