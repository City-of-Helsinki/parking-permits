from django.utils import timezone as tz

from . import constants
from .models import Customer, ParkingPermit
from .services.talpa import resolve_price_response

IMMEDIATELY = constants.StartType.IMMEDIATELY.value
DRAFT = constants.ParkingPermitStatus.DRAFT.value
VALID = constants.ParkingPermitStatus.VALID.value
PROCESSING = constants.ParkingPermitStatus.PROCESSING.value


def next_day():
    return tz.localtime(tz.now() + tz.timedelta(days=1))


class CustomerPermit:
    customer = None
    customer_permit_query = None

    def __init__(self, customer_id):
        self.customer = Customer.objects.get(id=customer_id)
        self.customer_permit_query = ParkingPermit.objects.filter(
            customer=self.customer, status__in=[VALID, PROCESSING, DRAFT]
        )

    def get(self):
        permits = []
        # Update the start_time to next day for all the draft permits
        for permit in self.customer_permit_query.order_by("start_time"):
            if permit.status == DRAFT:
                permit.start_time = next_day()
                permit.save(update_fields=["start_time"])
            permits.append(self._resolve_prices(permit))
        return permits

    def _resolve_prices(self, permit):
        total_price, monthly_price = permit.get_prices()
        permit.prices = resolve_price_response(total_price, monthly_price)
        return permit
