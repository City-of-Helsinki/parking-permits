from dateutil.relativedelta import relativedelta
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase
from django.utils import timezone as tz

from parking_permits_app import constants
from parking_permits_app.customer_permit import CustomerPermit
from parking_permits_app.exceptions import (
    InvalidContractType,
    InvalidUserZone,
    NonDraftPermitUpdateError,
    PermitCanNotBeDelete,
    PermitLimitExceeded,
)
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
CLOSED = constants.ParkingPermitStatus.CLOSED.value
PROCESSING = constants.ParkingPermitStatus.PROCESSING.value
IMMEDIATELY = constants.StartType.IMMEDIATELY.value
FROM = constants.StartType.FROM.value
OPEN_ENDED = constants.ContractType.OPEN_ENDED.value
FIXED_PERIOD = constants.ContractType.FIXED_PERIOD.value
BENSIN = constants.VehicleType.BENSIN.value


def previous_day():
    return tz.localtime(tz.now() - tz.timedelta(days=1))


def next_day():
    return tz.localtime(tz.now() + tz.timedelta(days=1))


def get_future(days=1):
    return tz.localtime(tz.now() + tz.timedelta(days=days))


def get_end_time(start, month=0):
    return tz.localtime(start + relativedelta(months=month))


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

    def test_customer_should_not_get_closed_permit(self):
        customer = CustomerFactory(first_name="Firstname", last_name="Lastname")
        ParkingPermitFactory(
            customer=customer,
            status=CLOSED,
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


class DeleteCustomerPermitTestCase(TestCase):
    def setUp(self):
        self.customer_a = CustomerFactory(first_name="Firstname A", last_name="")
        self.customer_b = CustomerFactory(first_name="Firstname B", last_name="")

        self.c_a_closed = ParkingPermitFactory(customer=self.customer_a, status=CLOSED)
        self.c_a_processing = ParkingPermitFactory(
            customer=self.customer_a, status=PROCESSING
        )
        self.c_a_draft = ParkingPermitFactory(
            customer=self.customer_a, status=DRAFT, primary_vehicle=False
        )
        self.c_a_valid = ParkingPermitFactory(customer=self.customer_a, status=VALID)
        self.c_b_draft = ParkingPermitFactory(customer=self.customer_b, status=DRAFT)

    def test_customer_a_can_not_delete_non_draft_permit(self):
        msg = "Non draft permit can not be deleted"
        with self.assertRaisesMessage(PermitCanNotBeDelete, msg):
            CustomerPermit(self.customer_a.id).delete(self.c_a_closed.id)

        with self.assertRaisesMessage(PermitCanNotBeDelete, msg):
            CustomerPermit(self.customer_a.id).delete(self.c_a_valid.id)

        with self.assertRaisesMessage(PermitCanNotBeDelete, msg):
            CustomerPermit(self.customer_a.id).delete(self.c_a_processing.id)

    def test_customer_a_can_delete_draft_permit(self):
        result = CustomerPermit(self.customer_a.id).delete(self.c_a_draft.id)
        self.assertEqual(result, True)

    def test_customer_a_can_not_delete_others_permit(self):
        with self.assertRaises(ObjectDoesNotExist):
            CustomerPermit(self.customer_a.id).delete(self.c_b_draft.id)


class UpdateCustomerPermitTestCase(TestCase):
    def setUp(self):
        self.cus_a = CustomerFactory(first_name="Firstname A", last_name="")
        self.cus_b = CustomerFactory(first_name="Firstname B", last_name="")

        self.c_a_draft = ParkingPermitFactory(
            customer=self.cus_a,
            status=DRAFT,
            parking_zone=self.cus_a.primary_address.zone,
        )
        self.c_a_can = ParkingPermitFactory(customer=self.cus_a, status=CLOSED)
        self.c_b_valid = ParkingPermitFactory(customer=self.cus_b, status=VALID)
        self.c_b_draft = ParkingPermitFactory(customer=self.cus_b, status=DRAFT)
        self.c_a_draft_sec = ParkingPermitFactory(
            customer=self.cus_a,
            status=DRAFT,
            primary_vehicle=False,
            parking_zone=self.cus_a.primary_address.zone,
        )

    def test_can_not_update_others_permit(self):
        data = {"consent_low_emission_accepted": True}
        with self.assertRaises(ObjectDoesNotExist):
            CustomerPermit(self.cus_a.id).update(data, self.c_b_draft.id)

    def test_can_update_consent_low_emission_accepted_for_a_permit(self):
        data = {"consent_low_emission_accepted": True}
        self.assertEqual(self.c_a_draft.consent_low_emission_accepted, False)
        res = CustomerPermit(self.cus_a.id).update(data, self.c_a_draft.id)
        self.assertEqual(res.consent_low_emission_accepted, True)

    def test_can_not_update_consent_low_emission_accepted_for_closed(
        self,
    ):
        data = {"consent_low_emission_accepted": True}
        with self.assertRaises(ObjectDoesNotExist):
            CustomerPermit(self.cus_a.id).update(data, self.c_a_can.id)

    def test_toggle_primary_vehicle_of_customer_a(self):
        data = {"primary_vehicle": True}
        self.assertEqual(self.c_a_draft.primary_vehicle, True)
        self.assertEqual(self.c_a_draft_sec.primary_vehicle, False)
        pri, sec = CustomerPermit(self.cus_a.id).update(data, self.c_a_can.id)

        # Check if they are same
        self.assertEqual(pri.id, self.c_a_draft.id)
        self.assertEqual(sec.id, self.c_a_draft_sec.id)

        self.assertEqual(pri.primary_vehicle, False)
        self.assertEqual(sec.primary_vehicle, True)

    def test_can_not_update_zone_id_of_drafts_if_not_in_his_address(self):
        self.zone = ParkingZoneFactory()
        data = {"zone_id": str(self.zone.id)}
        with self.assertRaisesMessage(InvalidUserZone, "Invalid user zone."):
            CustomerPermit(self.cus_a.id).update(data)

    def test_can_not_update_zone_id_of_valid_if_not_in_his_address(self):
        data = {"zone_id": str(self.cus_b.other_address.zone.id)}
        with self.assertRaisesMessage(InvalidUserZone, "Invalid user zone."):
            CustomerPermit(self.cus_a.id).update(data)

    def test_can_update_zone_id_of_all_drafts_with_zone_that_either_of_his_address_has(
        self,
    ):
        sec_add_zone = self.cus_a.other_address.zone
        pri_add_zone = self.cus_a.primary_address.zone
        data = {"zone_id": str(sec_add_zone.id)}
        self.assertEqual(self.c_a_draft.parking_zone, pri_add_zone)
        self.assertEqual(self.c_a_draft_sec.parking_zone, pri_add_zone)
        results = CustomerPermit(self.cus_a.id).update(data)
        for result in results:
            self.assertEqual(result.parking_zone, sec_add_zone)

    def test_can_not_update_zone_if_it_has_processing_or_valid_primary_permit(self):
        for status in [PROCESSING, VALID]:
            self.c_a_draft.status = status
            self.c_a_draft.save(update_fields=["status"])
            sec_add_zone = self.cus_a.other_address.zone
            pri_add_zone = self.cus_a.primary_address.zone
            data = {"zone_id": str(sec_add_zone.id)}
            msg = f"You can buy permit only for zone {pri_add_zone.name}"
            with self.assertRaisesMessage(InvalidUserZone, msg):
                CustomerPermit(self.cus_a.id).update(data)

    def test_all_draft_permit_to_have_same_immediately_start_type(self):
        tomorrow = next_day()
        data = {"start_type": IMMEDIATELY}
        permits = CustomerPermit(self.cus_a.id).update(data)
        for permit in permits:
            self.assertEqual(permit.start_type, IMMEDIATELY)
            self.assertGreaterEqual(permit.start_time, tomorrow)

    def test_draft_permits_to_start_after_three_days(self):
        after_3_days = get_future(3)
        utc_format = "%Y-%m-%dT%H:%M:%S.%fZ"
        data = {
            "start_type": FROM,
            "start_time": after_3_days.astimezone(tz.utc).strftime(utc_format),
        }
        permits = CustomerPermit(self.cus_a.id).update(data)
        for permit in permits:
            self.assertEqual(permit.start_type, FROM)
            self.assertGreaterEqual(permit.start_time, after_3_days)

    def test_draft_permits_to_be_max_2_weeks_in_future(self):
        after_3_weeks = get_end_time(next_day(), 3)
        utc_format = "%Y-%m-%dT%H:%M:%S.%fZ"
        data = {
            "start_type": FROM,
            "start_time": after_3_weeks.astimezone(tz.utc).strftime(utc_format),
        }
        permits = CustomerPermit(self.cus_a.id).update(data)
        time_after_2_weeks = get_end_time(next_day(), 2)
        for permit in permits:
            self.assertEqual(permit.start_type, FROM)
            self.assertLessEqual(permit.start_time, time_after_2_weeks)

    def test_should_have_same_contract_type_for_bulk_add(self):
        for contract in [OPEN_ENDED, FIXED_PERIOD]:
            data = {"contract_type": contract}
            permits = CustomerPermit(self.cus_a.id).update(data)
            for permit in permits:
                self.assertEqual(permit.contract_type, contract)
                self.assertEqual(permit.month_count, 1)

    def test_secondary_permit_can_be_either_open_ended_or_fixed_if_primary_is_open_ended(
        self,
    ):
        customer = CustomerFactory(first_name="Fake", last_name="")
        ParkingPermitFactory(customer=customer, status=VALID)
        secondary = ParkingPermitFactory(
            customer=customer,
            primary_vehicle=False,
        )
        permit_id = str(secondary.id)
        data = {"contract_type": OPEN_ENDED}
        CustomerPermit(customer.id).update(data, permit_id=permit_id)
        secondary.refresh_from_db()
        self.assertEqual(secondary.contract_type, OPEN_ENDED)

        data1 = {"contract_type": FIXED_PERIOD}
        CustomerPermit(customer.id).update(data1, permit_id=permit_id)
        secondary.refresh_from_db()
        self.assertEqual(secondary.contract_type, FIXED_PERIOD)

    def test_secondary_permit_can_be_only_fixed_if_primary_is_fixed_period(self):
        customer = CustomerFactory(first_name="Customer 1", last_name="")
        ParkingPermitFactory(
            customer=customer, status=VALID, contract_type=FIXED_PERIOD
        )
        secondary = ParkingPermitFactory(
            customer=customer, primary_vehicle=False, contract_type=FIXED_PERIOD
        )

        permit_id = str(secondary.id)
        msg = "Only FIXED_PERIOD is allowed"
        with self.assertRaisesMessage(InvalidContractType, msg):
            data = {"contract_type": OPEN_ENDED}
            CustomerPermit(customer.id).update(data, permit_id=permit_id)

        data1 = {"contract_type": FIXED_PERIOD}
        CustomerPermit(customer.id).update(data1, permit_id=permit_id)
        secondary.refresh_from_db()
        self.assertEqual(secondary.contract_type, FIXED_PERIOD)

    def test_non_draft_permit_contract_type_can_not_be_edited(self):
        customer = CustomerFactory(first_name="Customer 2", last_name="")
        permit = ParkingPermitFactory(customer=customer, status=VALID)
        data = {"contract_type": FIXED_PERIOD}
        permit_id = str(permit.id)
        msg = "This is not a draft permit and can not be edited"
        with self.assertRaisesMessage(NonDraftPermitUpdateError, msg):
            CustomerPermit(customer.id).update(data, permit_id=permit_id)

    def test_throw_error_for_missing_contract_type(self):
        msg = "Contract type is required"
        with self.assertRaisesMessage(InvalidContractType, msg):
            data = {"month_count": 1}
            CustomerPermit(self.cus_a.id).update(data, permit_id=str(self.c_a_draft.id))

    def test_primary_permit_can_have_max_12_month(self):
        customer = CustomerFactory(first_name="Customer", last_name="")
        permit = ParkingPermitFactory(customer=customer, contract_type=FIXED_PERIOD)
        data = {"month_count": 13, "contract_type": FIXED_PERIOD}
        permit_id = str(permit.id)
        CustomerPermit(customer.id).update(data, permit_id=permit_id)
        permit.refresh_from_db()
        self.assertEqual(permit.month_count, 12)

    def test_set_month_count_to_1_for_open_ended_contract(self):
        customer = CustomerFactory(first_name="Customer a", last_name="")
        permit = ParkingPermitFactory(customer=customer, contract_type=FIXED_PERIOD)
        data = {"month_count": 3, "contract_type": OPEN_ENDED}
        permit_id = str(permit.id)
        CustomerPermit(customer.id).update(data, permit_id=permit_id)
        permit.refresh_from_db()
        self.assertEqual(permit.month_count, 1)

    def test_second_permit_can_have_upto_12_month_if_primary_is_open_ended(self):
        customer = CustomerFactory()
        ParkingPermitFactory(customer=customer)
        secondary = ParkingPermitFactory(customer=customer, primary_vehicle=False)
        data = {"month_count": 12, "contract_type": FIXED_PERIOD}
        permit_id = str(secondary.id)
        CustomerPermit(customer.id).update(data, permit_id=permit_id)
        secondary.refresh_from_db()
        self.assertEqual(secondary.month_count, 12)

    def test_second_permit_can_not_have_permit_more_then_primary_if_primary_is_fixed_period(
        self,
    ):
        customer = CustomerFactory()
        ParkingPermitFactory(
            customer=customer,
            status=VALID,
            month_count=5,
            contract_type=FIXED_PERIOD,
            end_time=get_end_time(next_day(), 5),
        )
        secondary = ParkingPermitFactory(
            customer=customer, primary_vehicle=False, contract_type=FIXED_PERIOD
        )
        data = {"month_count": 12, "contract_type": FIXED_PERIOD}
        permit_id = str(secondary.id)
        CustomerPermit(customer.id).update(data, permit_id=permit_id)
        secondary.refresh_from_db()
        self.assertEqual(secondary.month_count, 5)
