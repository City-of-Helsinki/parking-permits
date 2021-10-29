from django.test import TestCase
from django.utils import timezone as tz

from parking_permits_app import constants
from parking_permits_app.customer_permit import CustomerPermit
from parking_permits_app.exceptions import InvalidUserZone, PermitLimitExceeded
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
OPEN_ENDED = constants.ContractType.OPEN_ENDED.value
FIXED_PERIOD = constants.ContractType.FIXED_PERIOD.value
BENSIN = constants.VehicleType.BENSIN.value


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


class CreateCustomerPermitTestCase(TestCase):
    def setUp(self):
        self.customer_a = CustomerFactory(
            first_name="Firstname A", last_name="Lastname 1"
        )
        self.customer_b = CustomerFactory(
            first_name="Firstname B", last_name="Lastname 2"
        )
        self.customer_c = CustomerFactory(
            first_name="Firstname C", last_name="Lastname 3"
        )
        self.customer_a_zone = self.customer_a.primary_address.zone
        self.vehicle_type = VehicleTypeFactory(type=BENSIN)
        self.zone = ParkingZoneFactory()
        self.vehicle_a = VehicleFactory(type=self.vehicle_type)
        PriceFactory(zone=self.zone)
        PriceFactory(zone=self.customer_a_zone)
        LowEmissionCriteriaFactory(vehicle_type=self.vehicle_type)
        ParkingPermitFactory(
            customer=self.customer_a,
            status=DRAFT,
            primary_vehicle=True,
            parking_zone=self.customer_a_zone,
            vehicle=self.vehicle_a,
        )
        self.customer_c_valid_primary_permit = ParkingPermitFactory(
            customer=self.customer_c,
            status=VALID,
            primary_vehicle=True,
            contract_type=FIXED_PERIOD,
            parking_zone=self.customer_c.primary_address.zone,
            vehicle=self.vehicle_a,
        )

    def test_customer_a_can_create_secondary_permit(self):
        customer_permit = CustomerPermit(self.customer_a.id)
        self.assertEqual(len(customer_permit.get()), 1)
        permit = CustomerPermit(self.customer_a.id).create(str(self.customer_a_zone.id))
        self.assertEqual(len(customer_permit.get()), 2)
        self.assertEqual(permit.primary_vehicle, False)

    def test_customer_a_can_not_create_permit_in_zone_outside_his_address(self):
        with self.assertRaisesMessage(InvalidUserZone, "Invalid user zone."):
            CustomerPermit(self.customer_a.id).create(self.zone.id)

    def test_customer_a_gets_error_for_exceeding_max_2_permit(self):
        msg = "You can have a max of 2 permits."
        with self.assertRaisesMessage(PermitLimitExceeded, msg):
            for i in range(0, 3):
                CustomerPermit(self.customer_a.id).create(str(self.customer_a_zone.id))

    def test_customer_b_can_not_buy_permit_to_other_zone_if_he_has_any_valid_permit_to_primary_address(
        self,
    ):
        vehicle = VehicleFactory(type=self.vehicle_type)
        primary_zone = self.customer_b.primary_address.zone
        ParkingPermitFactory(
            customer=self.customer_b,
            status=VALID,
            primary_vehicle=True,
            parking_zone=self.customer_b.primary_address.zone,
            vehicle=vehicle,
        )
        other_add_zone = self.customer_b.other_address.zone
        msg = f"You can buy permit only for zone {primary_zone.name}"
        with self.assertRaisesMessage(InvalidUserZone, msg):
            CustomerPermit(self.customer_b.id).create(str(other_add_zone.id))

    def test_customer_b_can_buy_permit_to_same_zone_that_he_has_at_least_one_valid_permit(
        self,
    ):
        primary_zone = self.customer_c.primary_address.zone
        permit = CustomerPermit(self.customer_c.id).create(str(primary_zone.id))
        self.assertEqual(
            permit.contract_type, self.customer_c_valid_primary_permit.contract_type
        )
        self.assertEqual(
            permit.primary_vehicle,
            not self.customer_c_valid_primary_permit.primary_vehicle,
        )
