from datetime import date, datetime, timedelta
from datetime import timezone as dt_tz
from unittest.mock import MagicMock

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, override_settings
from django.utils import timezone as tz
from django.utils.translation import gettext as _
from freezegun import freeze_time

from parking_permits.customer_permit import PRELIMINARY, CustomerPermit
from parking_permits.exceptions import (
    InvalidContractType,
    InvalidUserAddress,
    NonDraftPermitUpdateError,
    PermitCanNotBeDeleted,
    PermitCanNotBeExtended,
    TemporaryVehicleValidationError,
)
from parking_permits.models.parking_permit import (
    ContractType,
    ParkingPermit,
    ParkingPermitStartType,
    ParkingPermitStatus,
)
from parking_permits.models.product import ProductType
from parking_permits.tests.factories import (
    LowEmissionCriteriaFactory,
    ParkingZoneFactory,
)
from parking_permits.tests.factories.address import AddressFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import (
    TemporaryVehicleFactory,
    VehicleFactory,
    VehiclePowerTypeFactory,
)

DRAFT = ParkingPermitStatus.DRAFT
VALID = ParkingPermitStatus.VALID
CLOSED = ParkingPermitStatus.CLOSED
PAYMENT_IN_PROGRESS = ParkingPermitStatus.PAYMENT_IN_PROGRESS
IMMEDIATELY = ParkingPermitStartType.IMMEDIATELY
FROM = ParkingPermitStartType.FROM
OPEN_ENDED = ContractType.OPEN_ENDED
FIXED_PERIOD = ContractType.FIXED_PERIOD


def previous_day():
    return tz.localtime(tz.now() - tz.timedelta(days=1))


def next_day():
    return tz.localtime(tz.now() + tz.timedelta(days=1))


def get_future(days=1):
    return tz.localtime(tz.now() + tz.timedelta(days=days))


def get_end_time(start, month=0):
    return tz.localtime(start + relativedelta(months=month))


@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
class RemoveTemporaryVehicleTestCase(TestCase):
    def test_remove_temporary_vehicle(self):
        permit = ParkingPermitFactory()
        temp_vehicle = TemporaryVehicleFactory()
        permit.temp_vehicles.add(temp_vehicle)

        CustomerPermit(permit.customer.pk).remove_temporary_vehicle(permit.pk)

        temp_vehicle.refresh_from_db()
        self.assertFalse(temp_vehicle.is_active)


@freeze_time(tz.make_aware(datetime(2024, 1, 7)))
@override_settings(DEBUG_SKIP_PARKKIHUBI_SYNC=True)
class AddTemporaryVehicleTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vehicle = VehicleFactory()
        cls.start_time = tz.now()
        cls.end_time = cls.start_time + timedelta(days=7)
        cls.permit = ParkingPermitFactory(
            status=VALID,
            primary_vehicle=True,
            start_time=cls.start_time,
            end_time=cls.end_time,
        )

    def test_add_temporary_vehicle(self):
        self.assertTrue(
            CustomerPermit(self.permit.customer.pk).add_temporary_vehicle(
                self.permit.pk,
                self.vehicle.registration_number,
                self.start_time.isoformat(),
                self.end_time.isoformat(),
            )
        )

        temp_vehicle = self.permit.temp_vehicles.get()
        self.assertEqual(temp_vehicle.vehicle, self.vehicle)
        self.assertEqual(temp_vehicle.start_time, self.start_time)
        self.assertEqual(temp_vehicle.end_time, self.end_time)

    def test_add_temporary_vehicle_registration_exists(self):
        self.permit.vehicle = self.vehicle
        self.permit.save()

        self.assertRaises(
            TemporaryVehicleValidationError,
            CustomerPermit(self.permit.customer.pk).add_temporary_vehicle,
            self.permit.pk,
            self.vehicle.registration_number,
            self.start_time.isoformat(),
            self.end_time.isoformat(),
        )

        self.assertFalse(self.permit.temp_vehicles.exists())

    def test_add_temporary_vehicle_registration_exists_other_case(self):
        self.permit.vehicle = self.vehicle
        self.permit.save()

        self.assertRaises(
            TemporaryVehicleValidationError,
            CustomerPermit(self.permit.customer.pk).add_temporary_vehicle,
            self.permit.pk,
            self.vehicle.registration_number.lower(),
            self.start_time.isoformat(),
            self.end_time.isoformat(),
        )

        self.assertFalse(self.permit.temp_vehicles.exists())

    def test_add_temporary_vehicle_starts_before_now(self):
        now = tz.now()
        CustomerPermit(self.permit.customer.pk).add_temporary_vehicle(
            self.permit.pk,
            self.vehicle.registration_number,
            (now - timedelta(hours=1)).isoformat(),
            self.end_time.isoformat(),
        )

        self.assertTrue(self.permit.temp_vehicles.exists())

        vehicle = self.permit.temp_vehicles.first()
        self.assertEqual(vehicle.start_time, now)

    def test_add_temporary_vehicle_ends_before_starts(self):
        now = tz.now()
        CustomerPermit(self.permit.customer.pk).add_temporary_vehicle(
            self.permit.pk,
            self.vehicle.registration_number,
            self.start_time.isoformat(),
            (now - timedelta(hours=1)).isoformat(),
        )

        self.assertTrue(self.permit.temp_vehicles.exists())

        vehicle = self.permit.temp_vehicles.first()
        self.assertEqual(vehicle.start_time, now)
        self.assertEqual(vehicle.end_time, now + timedelta(hours=1))

    def test_add_temporary_vehicle_starts_before_permit(self):
        self.permit.start_time = self.permit.start_time + timedelta(days=3)
        self.permit.save()

        self.assertRaises(
            TemporaryVehicleValidationError,
            CustomerPermit(self.permit.customer.pk).add_temporary_vehicle,
            self.permit.pk,
            self.vehicle.registration_number,
            self.start_time.isoformat(),
            self.end_time.isoformat(),
        )

        self.assertFalse(self.permit.temp_vehicles.exists())

    def test_add_temporary_vehicle_more_than_one_over_a_year(self):
        temp_vehicles = TemporaryVehicleFactory.create_batch(
            2, start_time=self.start_time - timedelta(days=30 * 24)
        )
        self.permit.temp_vehicles.set(temp_vehicles)

        CustomerPermit(self.permit.customer.pk).add_temporary_vehicle(
            self.permit.pk,
            self.vehicle.registration_number,
            self.start_time.isoformat(),
            self.end_time.isoformat(),
        )

        self.assertEqual(self.permit.temp_vehicles.count(), 3)

    def test_add_temporary_vehicle_more_than_one_in_a_year(self):
        temp_vehicles = TemporaryVehicleFactory.create_batch(
            2, start_time=self.start_time - timedelta(days=30)
        )
        self.permit.temp_vehicles.set(temp_vehicles)

        self.assertRaises(
            TemporaryVehicleValidationError,
            CustomerPermit(self.permit.customer.pk).add_temporary_vehicle,
            self.permit.pk,
            self.vehicle.registration_number,
            self.start_time.isoformat(),
            self.end_time.isoformat(),
        )

        self.assertEqual(self.permit.temp_vehicles.count(), 2)


@freeze_time(tz.make_aware(datetime(2022, 1, 7)))
class GetCustomerPermitTestCase(TestCase):
    def setUp(self):
        self.customer_a = CustomerFactory(
            first_name="Firstname A", last_name="Lastname 1"
        )
        self.customer_b = CustomerFactory(
            first_name="Firstname B", last_name="Lastname B"
        )
        self.zone = ParkingZoneFactory()
        power_type = VehiclePowerTypeFactory(identifier="01", name="Bensin")
        self.vehicle_a = VehicleFactory(power_type=power_type)
        self.vehicle_b = VehicleFactory(power_type=power_type)
        self.vehicle_c = VehicleFactory(power_type=power_type)
        ProductFactory(
            zone=self.zone,
            type=ProductType.RESIDENT,
            start_date=date(2022, 1, 1),
            end_date=date(2022, 12, 31),
        )
        LowEmissionCriteriaFactory()
        ParkingPermitFactory(
            customer=self.customer_a,
            status=DRAFT,
            primary_vehicle=True,
            parking_zone=self.zone,
            vehicle=self.vehicle_a,
        )
        ParkingPermitFactory(
            customer=self.customer_a,
            status=PRELIMINARY,
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

    @override_settings(TRAFICOM_MOCK=True)
    def test_customer_a_should_get_only_his_draft_permit(self):
        permits = CustomerPermit(self.customer_a.id).get()
        self.assertEqual(len(permits), 2)

    @override_settings(TRAFICOM_MOCK=True)
    def test_customer_b_should_delete_draft_permit_that_is_created_before_today(self):
        query_set = ParkingPermit.objects.filter(
            customer=self.customer_b,
            status__in=[VALID, PAYMENT_IN_PROGRESS, DRAFT, PRELIMINARY],
        )
        self.assertEqual(query_set.count(), 1)
        ParkingPermitFactory(
            customer=self.customer_b,
            status=DRAFT,
            primary_vehicle=False,
            parking_zone=self.zone,
            vehicle=self.vehicle_b,
            start_type=IMMEDIATELY,
            start_time=previous_day(),
        )
        self.assertEqual(query_set.count(), 2)
        permits = CustomerPermit(self.customer_b.id).get()
        self.assertEqual(len(permits), 1)

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


@freeze_time(tz.make_aware(datetime(2022, 1, 7)))
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
        self.zone = ParkingZoneFactory()
        power_type = VehiclePowerTypeFactory(identifier="01", name="Bensin")
        self.vehicle_a = VehicleFactory(power_type=power_type)
        self.vehicle_b = VehicleFactory(power_type=power_type)
        ProductFactory(
            zone=self.zone,
            type=ProductType.RESIDENT,
            start_date=date(2022, 1, 1),
            end_date=date(2022, 12, 31),
        )
        ProductFactory(
            zone=self.customer_a_zone,
            type=ProductType.RESIDENT,
            start_date=date(2022, 1, 1),
            end_date=date(2022, 12, 31),
        )
        LowEmissionCriteriaFactory()
        ParkingPermitFactory(
            customer=self.customer_a,
            status=DRAFT,
            primary_vehicle=True,
            parking_zone=self.customer_a_zone,
            vehicle=self.vehicle_a,
        )
        self.customer_c_valid_primary_permit = ParkingPermitFactory(
            customer=self.customer_c,
            address=self.customer_c.primary_address,
            status=VALID,
            primary_vehicle=True,
            contract_type=FIXED_PERIOD,
            parking_zone=self.customer_c.primary_address.zone,
            end_time=date(2022, 3, 6),
            vehicle=self.vehicle_a,
        )

    def test_customer_a_can_not_create_permit_in_zone_outside_his_address(self):
        address = AddressFactory()
        with self.assertRaisesMessage(InvalidUserAddress, _("Invalid user address.")):
            CustomerPermit(self.customer_a.id).create(address.id, "ABC-123")

    @override_settings(TRAFICOM_MOCK=True, TRAFICOM_CHECK=False)
    def test_primary_permit(self):
        permit = CustomerPermit(self.customer_b.id).create(
            self.customer_b.primary_address.id,
            self.vehicle_a.registration_number,
        )

        self.assertTrue(permit.primary_vehicle)
        self.assertEqual(permit.customer, self.customer_b)
        self.assertEqual(permit.vehicle, self.vehicle_a)
        self.assertEqual(permit.end_time.date(), date(2022, 2, 6))

    @override_settings(TRAFICOM_MOCK=False, TRAFICOM_CHECK=False)
    def test_primary_permit_registration_number_without_dashes(self):
        service = CustomerPermit(self.customer_b.id)
        service.customer.fetch_vehicle_detail = MagicMock(return_value=self.vehicle_a)

        permit = service.create(
            self.customer_b.primary_address.id,
            self.vehicle_a.registration_number.replace("-", ""),
        )

        self.assertTrue(permit.primary_vehicle)
        self.assertEqual(permit.customer, self.customer_b)
        self.assertEqual(permit.vehicle, self.vehicle_a)
        self.assertEqual(permit.end_time.date(), date(2022, 2, 6))

    @override_settings(TRAFICOM_MOCK=True, TRAFICOM_CHECK=False)
    def test_secondary_permit(self):
        permit = CustomerPermit(self.customer_c.id).create(
            self.customer_c.primary_address.id,
            self.vehicle_b.registration_number,
        )

        self.assertFalse(permit.primary_vehicle)
        self.assertEqual(permit.customer, self.customer_c)
        self.assertEqual(permit.vehicle, self.vehicle_b)
        self.assertEqual(permit.end_time.date(), date(2022, 2, 6))


class DeleteCustomerPermitTestCase(TestCase):
    def setUp(self):
        self.customer_a = CustomerFactory(first_name="Firstname A", last_name="")
        self.customer_b = CustomerFactory(first_name="Firstname B", last_name="")

        self.c_a_closed = ParkingPermitFactory(customer=self.customer_a, status=CLOSED)
        self.c_a_payment_in_progress = ParkingPermitFactory(
            customer=self.customer_a, status=PAYMENT_IN_PROGRESS
        )
        self.c_a_draft = ParkingPermitFactory(
            customer=self.customer_a, status=DRAFT, primary_vehicle=False
        )
        self.c_a_preliminary = ParkingPermitFactory(
            customer=self.customer_a, status=PRELIMINARY
        )
        self.c_a_valid = ParkingPermitFactory(customer=self.customer_a, status=VALID)
        self.c_b_draft = ParkingPermitFactory(customer=self.customer_b, status=DRAFT)

    def test_customer_a_can_not_delete_non_draft_permit(self):
        msg = _("Non draft permit can not be deleted")
        with self.assertRaisesMessage(PermitCanNotBeDeleted, msg):
            CustomerPermit(self.customer_a.id).delete(self.c_a_closed.id)

        with self.assertRaisesMessage(PermitCanNotBeDeleted, msg):
            CustomerPermit(self.customer_a.id).delete(self.c_a_valid.id)

        with self.assertRaisesMessage(PermitCanNotBeDeleted, msg):
            CustomerPermit(self.customer_a.id).delete(self.c_a_payment_in_progress.id)

    def test_customer_a_can_delete_draft_permit(self):
        result = CustomerPermit(self.customer_a.id).delete(self.c_a_draft.id)
        self.assertEqual(result, True)

    def test_customer_a_can_delete_preliminary_permit(self):
        result = CustomerPermit(self.customer_a.id).delete(self.c_a_preliminary.id)
        self.assertEqual(result, True)

    def test_customer_a_can_not_delete_others_permit(self):
        with self.assertRaises(ObjectDoesNotExist):
            CustomerPermit(self.customer_a.id).delete(self.c_b_draft.id)


class UpdateCustomerPermitTestCase(TestCase):
    def setUp(self):
        self.cus_a = CustomerFactory(first_name="Firstname A", last_name="")
        self.cus_b = CustomerFactory(first_name="Firstname B", last_name="")
        zone_a = ParkingZoneFactory(name="A")
        zone_b = ParkingZoneFactory(name="B")

        self.c_a_draft = ParkingPermitFactory(
            customer=self.cus_a,
            status=DRAFT,
            address=self.cus_a.primary_address,
            parking_zone=self.cus_a.primary_address.zone,
        )
        self.c_a_closed = ParkingPermitFactory(
            customer=self.cus_a, status=CLOSED, parking_zone=zone_a
        )
        self.c_b_valid = ParkingPermitFactory(
            customer=self.cus_b, status=VALID, parking_zone=zone_b
        )
        self.c_b_preliminary = ParkingPermitFactory(
            customer=self.cus_b, status=PRELIMINARY
        )
        self.c_a_draft_sec = ParkingPermitFactory(
            customer=self.cus_a,
            status=DRAFT,
            primary_vehicle=False,
            address=self.cus_a.primary_address,
            parking_zone=self.cus_a.primary_address.zone,
        )

    def test_can_not_update_others_permit(self):
        data = {"consent_low_emission_accepted": True}
        with self.assertRaises(ObjectDoesNotExist):
            CustomerPermit(self.cus_a.id).update(data, self.c_b_preliminary.id)

    def test_can_update_consent_low_emission_accepted_for_a_permit(self):
        data = {"consent_low_emission_accepted": True}
        self.assertEqual(self.c_a_draft.consent_low_emission_accepted, False)
        res = CustomerPermit(self.cus_a.id).update(data, self.c_a_draft.id)
        self.assertEqual(res[0].consent_low_emission_accepted, True)

    def test_can_not_update_consent_low_emission_accepted_for_closed(
        self,
    ):
        data = {"consent_low_emission_accepted": True}
        with self.assertRaises(ObjectDoesNotExist):
            CustomerPermit(self.cus_a.id).update(data, self.c_a_closed.id)

    def test_can_update_preliminary_permit(self):
        data = {"consent_low_emission_accepted": True}
        self.assertEqual(self.c_b_preliminary.consent_low_emission_accepted, False)
        res = CustomerPermit(self.cus_b.id).update(data, self.c_b_preliminary.id)
        self.assertEqual(res[0].consent_low_emission_accepted, True)

    def test_toggle_primary_vehicle_of_customer_a(self):
        data = {"primary_vehicle": True}
        self.assertEqual(self.c_a_draft.primary_vehicle, True)
        self.assertEqual(self.c_a_draft_sec.primary_vehicle, False)
        pri, sec = CustomerPermit(self.cus_a.id).update(data, self.c_a_closed.id)

        # Check if they are same
        self.assertEqual(pri.id, self.c_a_draft.id)
        self.assertEqual(sec.id, self.c_a_draft_sec.id)

        self.assertEqual(pri.primary_vehicle, False)
        self.assertEqual(sec.primary_vehicle, True)

    def test_can_not_update_address_id_of_drafts_if_not_in_his_address(self):
        address = AddressFactory()
        data = {"address_id": str(address.id)}
        with self.assertRaisesMessage(InvalidUserAddress, _("Invalid user address.")):
            CustomerPermit(self.cus_a.id).update(data)

    def test_can_not_update_address_id_of_valid_if_not_in_his_address(self):
        data = {"address_id": str(self.cus_b.other_address.id)}
        with self.assertRaisesMessage(InvalidUserAddress, _("Invalid user address.")):
            CustomerPermit(self.cus_a.id).update(data)

    def test_can_update_zone_id_of_all_drafts_with_zone_that_either_of_his_address_has(
        self,
    ):
        sec_add_id = self.cus_a.other_address.id
        pri_add_id = self.cus_a.primary_address.id
        data = {"address_id": str(sec_add_id)}
        self.assertEqual(self.c_a_draft.address_id, pri_add_id)
        self.assertEqual(self.c_a_draft_sec.address_id, pri_add_id)
        results = CustomerPermit(self.cus_a.id).update(data)
        for result in results:
            self.assertEqual(result.address_id, str(sec_add_id))

    def test_can_not_update_zone_if_it_has_payment_in_progress_or_valid_primary_permit(
        self,
    ):
        for status in [PAYMENT_IN_PROGRESS, VALID]:
            self.c_a_draft.status = status
            self.c_a_draft.save(update_fields=["status"])
            data = {"address_id": str(self.cus_a.other_address.id)}
            msg = _("You can buy permit only for address %(primary_address)s.") % {
                "primary_address": self.cus_a.primary_address
            }
            with self.assertRaisesMessage(InvalidUserAddress, msg):
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
            "start_time": after_3_days.astimezone(dt_tz.utc).strftime(utc_format),
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
            "start_time": after_3_weeks.astimezone(dt_tz.utc).strftime(utc_format),
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
        msg = _("Only %(fixed_period)s is allowed") % {"fixed_period": FIXED_PERIOD}
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
        msg = _("This is not a draft permit and can not be edited")
        with self.assertRaisesMessage(NonDraftPermitUpdateError, msg):
            CustomerPermit(customer.id).update(data, permit_id=permit_id)

    def test_throw_error_for_missing_contract_type(self):
        msg = _("Contract type is required")
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


class ExtendCustomerPermitTestCase(TestCase):
    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_ok(self):
        now = tz.now()
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=now,
            end_time=now + timedelta(days=10),
        )
        permit.address = permit.customer.primary_address
        permit.save()
        ProductFactory(
            zone=permit.parking_zone,
            type=ProductType.RESIDENT,
            start_date=(now - timedelta(days=360)).date(),
            end_date=(now + timedelta(days=360)).date(),
        )
        result = CustomerPermit(permit.customer_id).create_permit_extension_request(
            permit.pk, 3
        )
        self.assertTrue(result)
        ext_request = permit.get_pending_extension_requests().first()
        self.assertEqual(ext_request.month_count, 3)

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_exceeds_max_month_count(self):
        now = tz.now()
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=now,
            end_time=now + timedelta(days=10),
        )
        ProductFactory(
            zone=permit.parking_zone,
            type=ProductType.RESIDENT,
            start_date=(now - timedelta(days=360)).date(),
            end_date=(now + timedelta(days=360)).date(),
        )
        self.assertRaises(
            PermitCanNotBeExtended,
            CustomerPermit(permit.customer_id).create_permit_extension_request,
            permit.pk,
            13,
        )
        self.assertFalse(permit.get_pending_extension_requests().exists())

    @override_settings(PERMIT_EXTENSIONS_ENABLED=True)
    def test_invalid(self):
        now = tz.now()
        permit = ParkingPermitFactory(
            status=ParkingPermitStatus.VALID,
            contract_type=ContractType.FIXED_PERIOD,
            start_time=now,
            end_time=now + timedelta(days=30),
        )
        self.assertRaises(
            PermitCanNotBeExtended,
            CustomerPermit(permit.customer_id).create_permit_extension_request,
            permit.pk,
            3,
        )
        self.assertFalse(permit.get_pending_extension_requests().exists())
