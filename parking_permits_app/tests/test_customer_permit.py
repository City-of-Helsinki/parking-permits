from django.test import TestCase
from django.utils import timezone as tz

from parking_permits_app import constants
from parking_permits_app.customer_permit import CustomerPermit
from parking_permits_app.tests.factories import (
    LowEmissionCriteriaFactory,
    ParkingZoneFactory,
    PriceFactory,
)
from parking_permits_app.tests.factories.customer import CustomerFactory
from parking_permits_app.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits_app.tests.factories.vehicle import (
    VehicleFactory,
    VehicleTypeFactory,
)

DRAFT = constants.ParkingPermitStatus.DRAFT.value
VALID = constants.ParkingPermitStatus.VALID.value
CANCELLED = constants.ParkingPermitStatus.CANCELLED.value
EXPIRED = constants.ParkingPermitStatus.EXPIRED.value
PROCESSING = constants.ParkingPermitStatus.PROCESSING.value
IMMEDIATELY = constants.StartType.IMMEDIATELY.value


def previous_day():
    return tz.localtime(tz.now() - tz.timedelta(days=1))


class GetCustomerPermitTestCase(TestCase):
    def setUp(self):
        self.customer_a = CustomerFactory(
            first_name="Firstname A", last_name="Lastname 1"
        )
        self.customer_b = CustomerFactory(
            first_name="Firstname B", last_name="Lastname B"
        )
        self.vehicle_type = VehicleTypeFactory()
        self.zone = ParkingZoneFactory()
        self.vehicle_a = VehicleFactory(type=self.vehicle_type)
        self.vehicle_b = VehicleFactory(type=self.vehicle_type)
        self.vehicle_c = VehicleFactory(type=self.vehicle_type)
        PriceFactory(zone=self.zone)
        LowEmissionCriteriaFactory(vehicle_type=self.vehicle_type)
        ParkingPermitFactory(
            customer=self.customer_a,
            status=DRAFT,
            primary_vehicle=True,
            parking_zone=self.zone,
            vehicle=self.vehicle_a,
        )
        ParkingPermitFactory(
            customer=self.customer_a,
            status=DRAFT,
            primary_vehicle=False,
            parking_zone=self.zone,
            vehicle=self.vehicle_b,
        )
        ParkingPermitFactory(
            customer=self.customer_b,
            status=VALID,
            primary_vehicle=True,
            parking_zone=self.zone,
            vehicle=self.vehicle_b,
        )

    def test_customer_a_should_get_only_his_draft_permit(self):
        permits = CustomerPermit(self.customer_a.id).get()
        self.assertEqual(len(permits), 2)

    def test_customer_b_start_time_of_only_draft_should_be_next_day(self):
        create_d_permit = ParkingPermitFactory(
            customer=self.customer_b,
            status=DRAFT,
            primary_vehicle=False,
            parking_zone=self.zone,
            vehicle=self.vehicle_b,
            start_type=IMMEDIATELY,
            start_time=previous_day(),
        )
        permits = CustomerPermit(self.customer_b.id).get()
        draft = next(permit for permit in permits if permit.id == create_d_permit.id)
        valid = next(permit for permit in permits if permit.status == VALID)

        self.assertEqual(len(permits), 2)
        self.assertGreater(draft.start_time, tz.now())
        self.assertLessEqual(valid.start_time, tz.now())

    def test_customer_should_not_get_canceled_or_expired_permit(self):
        customer = CustomerFactory(first_name="Firstname", last_name="Lastname")
        ParkingPermitFactory(
            customer=customer,
            status=CANCELLED,
            primary_vehicle=True,
            parking_zone=self.zone,
        )
        ParkingPermitFactory(
            customer=customer,
            status=EXPIRED,
            primary_vehicle=True,
            parking_zone=self.zone,
        )
        permits = CustomerPermit(customer.id).get()
        self.assertEqual(len(permits), 0)
