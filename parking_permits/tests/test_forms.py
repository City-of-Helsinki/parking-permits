from datetime import timedelta
from datetime import timezone as dt_tz

import pytest
from django.test import TestCase
from django.utils import timezone

from parking_permits.forms import (
    CustomerSearchForm,
    OrderSearchForm,
    PdfExportForm,
    PermitSearchForm,
    RefundSearchForm,
)
from parking_permits.models.order import OrderPaymentType
from parking_permits.models.parking_permit import (
    ContractType,
    ParkingPermitStatus,
    ParkingPermitType,
)
from parking_permits.tests.factories import ParkingZoneFactory
from parking_permits.tests.factories.address import AddressFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.order import OrderFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.refund import RefundFactory
from parking_permits.tests.factories.vehicle import (
    TemporaryVehicleFactory,
    VehicleFactory,
)
from users.models import ParkingPermitGroups


class PdfExportFormTestCase(TestCase):
    def test_form_is_valid_when_valid_data_provided(self):
        data = {
            "data_type": "permit",
            "object_id": 1,
        }
        form = PdfExportForm(data)
        self.assertTrue(form.is_valid())

    def test_form_not_valid_when_data_type_not_provided(self):
        data = {
            "object_id": 1,
        }
        form = PdfExportForm(data)
        self.assertFalse(form.is_valid())

    def test_form_not_valid_when_object_id_not_provided(self):
        data = {
            "data_type": "permit",
        }
        form = PdfExportForm(data)
        self.assertFalse(form.is_valid())


class OrderSearchFormDistinctOrdersTestCase(TestCase):
    def test_return_only_distinct_results_on_orders_with_multiple_permits(self):
        order = OrderFactory()

        # Create two permits for the same order and assert that the queryset returns only one result.
        ParkingPermitFactory(orders=[order], contract_type=ContractType.OPEN_ENDED)
        ParkingPermitFactory(orders=[order], contract_type=ContractType.OPEN_ENDED)

        form = OrderSearchForm({"contract_types": "OPEN_ENDED"})
        self.assertTrue(form.is_valid())
        qs = form.get_queryset()
        self.assertEqual(len(qs), 1)

    def test_return_only_distinct_results_on_orders_with_multiple_permits_with_order_by(
        self,
    ):
        # Create four orders with two permits each.
        for name in ["B", "A", "D", "C"]:
            parking_zone = ParkingZoneFactory(name=name)
            order = OrderFactory()
            ParkingPermitFactory(
                orders=[order],
                contract_type=ContractType.OPEN_ENDED,
                parking_zone=parking_zone,
            )
            ParkingPermitFactory(
                orders=[order],
                contract_type=ContractType.OPEN_ENDED,
                parking_zone=parking_zone,
            )

        # Find open-ended orders and sort by parking zone name.
        form = OrderSearchForm(
            {
                "contract_types": "OPEN_ENDED",
                "order_direction": "ASC",
                "order_field": "parkingZone",
            }
        )
        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(len(qs), 4)
        for idx, name in enumerate(["A", "B", "C", "D"]):
            self.assertEqual(name, qs[idx].permits.first().parking_zone.name)


class PermitSearchFormTextSearch(TestCase):
    def test_search_permit_id(self):
        permit = ParkingPermitFactory(
            id="80000001",
        )

        form = PermitSearchForm({"q": str(permit.pk)})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), permit)

    def test_search_customer_name(self):
        customer = CustomerFactory(first_name="Seppo", last_name="Taalasmaa")

        permit = ParkingPermitFactory(
            customer=customer,
        )

        form = PermitSearchForm({"q": "Seppo"})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), permit)

    def test_search_customer_name_with_inspector_role(self):
        customer = CustomerFactory(first_name="Seppo", last_name="Taalasmaa")

        ParkingPermitFactory(
            customer=customer,
        )

        form = PermitSearchForm(
            {"q": "Seppo", "user_role": ParkingPermitGroups.INSPECTORS}
        )

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 0)

    def test_search_multiple_values(self):
        customer = CustomerFactory(first_name="Seppo", last_name="Taalasmaa")

        permit = ParkingPermitFactory(
            customer=customer,
        )

        form = PermitSearchForm({"q": "Taalasmaa Seppo"})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), permit)

    def test_search_multiple_values_not_all_correct(self):
        customer = CustomerFactory(first_name="Seppo", last_name="Koski")

        ParkingPermitFactory(
            customer=customer,
        )

        form = PermitSearchForm({"q": "Taalasmaa Seppo"})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 0)

    def test_search_customer_national_id_number(self):
        customer = CustomerFactory(
            first_name="Seppo",
            last_name="Taalasmaa",
            national_id_number="02051951-A111B",
        )

        permit = ParkingPermitFactory(
            customer=customer,
        )

        form = PermitSearchForm({"q": customer.national_id_number})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), permit)

    def test_search_customer_national_id_number_mixed_case(self):
        customer = CustomerFactory(
            first_name="Seppo",
            last_name="Taalasmaa",
            national_id_number="02051951-a111b",
        )

        permit = ParkingPermitFactory(
            customer=customer,
        )

        form = PermitSearchForm({"q": customer.national_id_number})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), permit)

    def test_search_customer_national_id_number_with_inspector_role(self):
        customer = CustomerFactory(
            first_name="Seppo",
            last_name="Taalasmaa",
            national_id_number="02051951-A111B",
        )

        ParkingPermitFactory(
            customer=customer,
        )

        form = PermitSearchForm(
            {
                "q": customer.national_id_number,
                "user_role": ParkingPermitGroups.INSPECTORS,
            }
        )

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 0)

    def test_search_vehicle(self):
        registration_number = "YLH-371"
        vehicle = VehicleFactory(registration_number=registration_number)

        permit = ParkingPermitFactory(vehicle=vehicle)
        form = PermitSearchForm({"q": registration_number})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), permit)

    def test_search_vehicle_lower_case(self):
        registration_number = "YLH-371"
        vehicle = VehicleFactory(registration_number=registration_number)

        permit = ParkingPermitFactory(vehicle=vehicle)
        form = PermitSearchForm({"q": "ylh-371"})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), permit)

    def test_search_temp_vehicle_lower_case(self):
        registration_number = "YLH-371"
        now = timezone.now()
        temp_vehicle = TemporaryVehicleFactory(
            vehicle__registration_number=registration_number,
            is_active=True,
            start_time=now - timedelta(days=3),
            end_time=now + timedelta(days=3),
        )

        permit = ParkingPermitFactory()
        permit.temp_vehicles.add(temp_vehicle)
        form = PermitSearchForm({"q": "ylh-371"})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), permit)

    def test_search_vehicle_lower_case_with_inspector_role(self):
        registration_number = "YLH-371"
        vehicle = VehicleFactory(registration_number=registration_number)

        permit = ParkingPermitFactory(vehicle=vehicle)
        form = PermitSearchForm(
            {"q": "ylh-371", "user_role": ParkingPermitGroups.INSPECTORS}
        )

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), permit)

    def test_search_status(self):
        registration_number = "YLH-371"
        vehicle = VehicleFactory(registration_number=registration_number)
        permit = ParkingPermitFactory(vehicle=vehicle, status=ParkingPermitStatus.VALID)
        ParkingPermitFactory(
            vehicle=vehicle, status=ParkingPermitStatus.PAYMENT_IN_PROGRESS
        )
        ParkingPermitFactory(vehicle=vehicle, status=ParkingPermitStatus.CLOSED)
        ParkingPermitFactory(vehicle=vehicle, status=ParkingPermitStatus.DRAFT)

        form = PermitSearchForm(
            {"q": registration_number, "status": ParkingPermitStatus.VALID}
        )

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), permit)


class OrderSearchFormTextSearch(TestCase):
    def setUp(self):
        self.address = AddressFactory(street_name="Pihlajakatu", street_number="23")

    def test_search_permit_id(self):
        order = OrderFactory()

        ParkingPermitFactory(
            orders=[order],
            address=self.address,
            customer=order.customer,
        )

        form = OrderSearchForm({"q": str(order.pk)})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)

    def test_search_customer_name(self):
        customer = CustomerFactory(first_name="Seppo", last_name="Taalasmaa")
        order = OrderFactory(customer=customer)

        ParkingPermitFactory(
            orders=[order],
            address=self.address,
            customer=customer,
        )

        form = OrderSearchForm({"q": "Seppo"})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), order)

    def test_search_multiple_values(self):
        customer = CustomerFactory(first_name="Seppo", last_name="Taalasmaa")
        order = OrderFactory(customer=customer)

        ParkingPermitFactory(
            orders=[order],
            address=self.address,
            customer=customer,
        )

        form = OrderSearchForm({"q": "Taalasmaa Seppo"})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), order)

    def test_search_multiple_values_not_all_correct(self):
        customer = CustomerFactory(first_name="Seppo", last_name="Koski")
        order = OrderFactory(customer=customer)

        ParkingPermitFactory(
            orders=[order],
            address=self.address,
            customer=customer,
        )

        form = OrderSearchForm({"q": "Taalasmaa Seppo"})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 0)

    def test_search_customer_national_id_number(self):
        customer = CustomerFactory(
            first_name="Seppo",
            last_name="Taalasmaa",
            national_id_number="02051951-A111B",
        )
        order = OrderFactory(customer=customer)

        ParkingPermitFactory(
            orders=[order],
            address=self.address,
            customer=customer,
        )

        form = OrderSearchForm({"q": customer.national_id_number})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), order)

    def test_search_vehicle(self):
        customer = CustomerFactory()
        order = OrderFactory(customer=customer, vehicles=["YLH-371"])

        form = OrderSearchForm({"q": "YLH-371"})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), order)

    def test_search_multiple_vehicles(self):
        customer = CustomerFactory()
        order = OrderFactory(customer=customer, vehicles=["YLH-371", "CYV-111"])

        form = OrderSearchForm({"q": "YLH-371 CYV-111"})

        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), order)


class OrderSearchFormSortTestCase(TestCase):
    def test_sort_by_address_name(self):
        for name, number in [
            ("B", "2"),
            ("A", "2"),
            ("D", "1"),
            ("A", "1"),
            ("C", "1"),
        ]:
            address = AddressFactory(street_name=name, street_number=number)
            order = OrderFactory()
            ParkingPermitFactory(orders=[order], address=address)

        # Find open-ended orders and sort by parking zone name.
        form = OrderSearchForm(
            {
                "order_direction": "ASC",
                "order_field": "address",
                "payment_types": OrderPaymentType.CASHIER_PAYMENT,
            }
        )
        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(len(qs), 5)
        for idx, (name, number) in enumerate(
            [("A", "1"), ("A", "2"), ("B", "2"), ("C", "1"), ("D", "1")]
        ):
            self.assertEqual(name, qs[idx].permits.first().address.street_name)
            self.assertEqual(number, qs[idx].permits.first().address.street_number)

    def test_sort_by_contract_type(self):
        for permit_type in [
            ParkingPermitType.COMPANY,
            ParkingPermitType.RESIDENT,
            ParkingPermitType.COMPANY,
            ParkingPermitType.RESIDENT,
        ]:
            ParkingPermitFactory(orders=[OrderFactory()], type=permit_type)

        # Find open-ended orders and sort by parking zone name.
        form = OrderSearchForm(
            {
                "order_direction": "ASC",
                "order_field": "permitType",
                "payment_types": OrderPaymentType.CASHIER_PAYMENT,
            }
        )
        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(len(qs), 4)
        for idx, permit_type in enumerate(
            [
                ParkingPermitType.COMPANY,
                ParkingPermitType.COMPANY,
                ParkingPermitType.RESIDENT,
                ParkingPermitType.RESIDENT,
            ]
        ):
            self.assertEqual(permit_type, qs[idx].permits.first().type)

    def test_sort_by_parking_zone_name(self):
        for name in ["B", "A", "D", "C"]:
            ParkingPermitFactory(
                orders=[OrderFactory()], parking_zone=ParkingZoneFactory(name=name)
            )

        form = OrderSearchForm(
            {
                "order_direction": "ASC",
                "order_field": "parkingZone",
                "payment_types": OrderPaymentType.CASHIER_PAYMENT,
            }
        )
        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(len(qs), 4)
        for idx, name in enumerate(["A", "B", "C", "D"]):
            self.assertEqual(name, qs[idx].permits.first().parking_zone.name)

    def test_sort_by_permit(self):
        # Create orders, store them in a list and change their order.
        orders = [OrderFactory() for _ in range(0, 5)]
        orders[2], orders[4] = orders[4], orders[2]

        # Create the parking permits and store their IDs. This is the expected order of the order search as well.
        permit_ids = [ParkingPermitFactory(orders=[order]).pk for order in orders]

        form = OrderSearchForm(
            {
                "order_direction": "ASC",
                "order_field": "permits",
                "payment_types": OrderPaymentType.CASHIER_PAYMENT,
            }
        )
        self.assertTrue(form.is_valid())

        qs = form.get_queryset()
        self.assertEqual(len(qs), 5)
        for idx, permit_id in enumerate(permit_ids):
            self.assertEqual(permit_id, qs[idx].permits.first().pk)


class OrderSearchFormDateRangeTestCase(TestCase):
    def run_date_range_sub_tests(self, order, form_data, sub_tests):
        """Utility function for running a suite of subtests specifically for the date range search.

        Creates a single parking permit with a start and an optional end time, assigns it to the given order,
        and then asserts the result count."""
        form = OrderSearchForm(form_data)
        self.assertTrue(form.is_valid())

        for sub_test in sub_tests:
            permit_args = sub_test["permit"]
            start_time = timezone.datetime(*permit_args["start_time"], tzinfo=dt_tz.utc)
            # Set end_time only if its arguments exist in the subtest data.
            end_time = (
                timezone.datetime(*args, tzinfo=dt_tz.utc)
                if (args := permit_args.get("end_time"))
                else None
            )
            permit = ParkingPermitFactory(
                orders=[order], start_time=start_time, end_time=end_time
            )

            qs = form.get_queryset()

            with self.subTest(form_data=form_data, **sub_test):
                self.assertEqual(qs.count(), sub_test["expected_count"])

            permit.delete()

    def test_form_start_date_search(self):
        order = OrderFactory()

        self.run_date_range_sub_tests(
            order,
            form_data={"start_date": "2000-01-01"},
            sub_tests=[
                {
                    "msg": "Permit starts in the past",
                    "permit": {"start_time": (1999, 12, 1)},
                    "expected_count": 1,
                },
                {
                    "msg": "Permit starts in the future",
                    "permit": {"start_time": (2001, 1, 1)},
                    "expected_count": 1,
                },
                {
                    "msg": "Permit starts in the past, ends in the future",
                    "permit": {"start_time": (1999, 1, 1), "end_time": (2001, 1, 1)},
                    "expected_count": 1,
                },
                {
                    "msg": "Permit both starts and ends in the past",
                    "permit": {"start_time": (1999, 12, 1), "end_time": (1999, 12, 31)},
                    "expected_count": 0,
                },
                {
                    "msg": "Permit both starts and ends in the future",
                    "permit": {"start_time": (2001, 1, 1), "end_time": (2002, 1, 1)},
                    "expected_count": 1,
                },
            ],
        )

    def test_form_end_date_search(self):
        order = OrderFactory()

        self.run_date_range_sub_tests(
            order,
            form_data={"end_date": "2000-01-01"},
            sub_tests=[
                {
                    "msg": "Permit starts in the past",
                    "permit": {"start_time": (1999, 12, 1)},
                    "expected_count": 1,
                },
                {
                    "msg": "Permit starts in the future",
                    "permit": {"start_time": (2001, 1, 1)},
                    "expected_count": 0,
                },
                {
                    "msg": "Permit starts in the past, ends in the future",
                    "permit": {"start_time": (1999, 1, 1), "end_time": (2001, 1, 1)},
                    "expected_count": 1,
                },
                {
                    "msg": "Permit both starts and ends in the past",
                    "permit": {"start_time": (1999, 12, 1), "end_time": (1999, 12, 31)},
                    "expected_count": 1,
                },
                {
                    "msg": "Permit both starts and ends in the future",
                    "permit": {"start_time": (2001, 1, 1), "end_time": (2002, 1, 1)},
                    "expected_count": 0,
                },
            ],
        )

    def test_form_with_start_date_and_end_date_search(self):
        order = OrderFactory()

        self.run_date_range_sub_tests(
            order,
            form_data={"start_date": "2000-01-01", "end_date": "2000-01-31"},
            sub_tests=[
                {
                    "msg": "Permit starts in the past",
                    "permit": {"start_time": (1999, 12, 1)},
                    "expected_count": 1,
                },
                {
                    "msg": "Permit starts between the start and end date",
                    "permit": {"start_time": (2000, 1, 16)},
                    "expected_count": 1,
                },
                {
                    "msg": "Permit starts after end date",
                    "permit": {"start_time": (2000, 2, 1)},
                    "expected_count": 0,
                },
                {
                    "msg": "Permit starts in the past, ends before the end date",
                    "permit": {"start_time": (1999, 12, 1), "end_time": (2000, 1, 16)},
                    "expected_count": 1,
                },
                {
                    "msg": "Permit starts in the past, ends after the end date",
                    "permit": {"start_time": (1999, 12, 1), "end_time": (2000, 2, 1)},
                    "expected_count": 1,
                },
                {
                    "msg": "Permit both starts and ends in the past",
                    "permit": {"start_time": (1999, 12, 1), "end_time": (1999, 12, 31)},
                    "expected_count": 0,
                },
                {
                    "msg": "Permit both starts and ends after the end date",
                    "permit": {"start_time": (2100, 1, 1), "end_time": (2200, 1, 1)},
                    "expected_count": 0,
                },
            ],
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "name",
    [
        pytest.param("doe", id="last-name"),
        pytest.param("john", id="first-name"),
        pytest.param("john doe", id="full-name"),
        pytest.param("doe john", id="full-name-reverse"),
    ],
)
@pytest.mark.django_db
def test_customer_search_form_search_by_name(name):
    CustomerFactory(first_name="Foo", last_name="Bar")
    customer = CustomerFactory(first_name="John", last_name="Doe")
    form = CustomerSearchForm({"name": name})

    assert form.is_valid()
    qs = form.get_queryset()
    assert len(qs) == 1
    assert qs.first() == customer


@pytest.mark.django_db
def test_customer_search_form_should_return_empty_by_default():
    CustomerFactory()
    form = CustomerSearchForm({})

    assert form.is_valid()
    qs = form.get_queryset()
    assert len(qs) == 0


@pytest.mark.django_db
def test_order_search_form_should_return_empty_by_default():
    OrderFactory()
    form = OrderSearchForm({})

    assert form.is_valid()
    qs = form.get_queryset()
    assert len(qs) == 0


@pytest.mark.django_db
def test_refund_search_form_should_return_empty_by_default():
    RefundFactory()
    form = RefundSearchForm({})

    assert form.is_valid()
    qs = form.get_queryset()
    assert len(qs) == 0


@pytest.mark.django_db
def test_permit_search_form_should_return_empty_by_default():
    ParkingPermitFactory()
    form = PermitSearchForm({})

    assert form.is_valid()
    qs = form.get_queryset()
    assert len(qs) == 0
