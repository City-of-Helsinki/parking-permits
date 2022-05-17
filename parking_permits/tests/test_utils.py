from datetime import date

from django.test import TestCase

from parking_permits.models import ParkingPermit
from parking_permits.models.parking_permit import ParkingPermitStatus
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.utils import (
    apply_filtering,
    apply_ordering,
    diff_months_ceil,
    diff_months_floor,
    find_next_date,
)


class ApplyingOrderingTestCase(TestCase):
    def setUp(self):
        customer_1 = CustomerFactory(first_name="Firstname B", last_name="Lastname 1")
        customer_2 = CustomerFactory(first_name="Firstname A", last_name="Lastname 2")
        customer_3 = CustomerFactory(first_name="Firstname A", last_name="Lastname 3")
        ParkingPermitFactory(customer=customer_1)
        ParkingPermitFactory(customer=customer_2)
        ParkingPermitFactory(customer=customer_3)

    def test_apply_asc_ordering(self):
        order_by = {
            "order_fields": ["customer__first_name", "customer__last_name"],
            "order_direction": "ASC",
        }
        qs = ParkingPermit.objects.all()
        ordered_qs = apply_ordering(qs, order_by)
        self.assertEqual(ordered_qs[0].customer.first_name, "Firstname A")
        self.assertEqual(ordered_qs[0].customer.last_name, "Lastname 2")
        self.assertEqual(ordered_qs[1].customer.first_name, "Firstname A")
        self.assertEqual(ordered_qs[1].customer.last_name, "Lastname 3")
        self.assertEqual(ordered_qs[2].customer.first_name, "Firstname B")
        self.assertEqual(ordered_qs[2].customer.last_name, "Lastname 1")

    def test_apply_desc_ordering(self):
        order_by = {
            "order_fields": ["customer__first_name", "customer__last_name"],
            "order_direction": "DESC",
        }
        qs = ParkingPermit.objects.all()
        ordered_qs = apply_ordering(qs, order_by)
        self.assertEqual(ordered_qs[0].customer.first_name, "Firstname B")
        self.assertEqual(ordered_qs[0].customer.last_name, "Lastname 1")
        self.assertEqual(ordered_qs[1].customer.first_name, "Firstname A")
        self.assertEqual(ordered_qs[1].customer.last_name, "Lastname 3")
        self.assertEqual(ordered_qs[2].customer.first_name, "Firstname A")
        self.assertEqual(ordered_qs[2].customer.last_name, "Lastname 2")


class ApplyingFilteringTestCase(TestCase):
    def setUp(self):
        customer_1 = CustomerFactory(first_name="Firstname B", last_name="Lastname 1")
        customer_2 = CustomerFactory(first_name="Firstname A", last_name="Lastname 2")
        customer_3 = CustomerFactory(first_name="Firstname A", last_name="Lastname 3")
        ParkingPermitFactory(customer=customer_1, status=ParkingPermitStatus.DRAFT)
        ParkingPermitFactory(customer=customer_2, status=ParkingPermitStatus.VALID)
        ParkingPermitFactory(customer=customer_3, status=ParkingPermitStatus.DRAFT)

    def test_search_with_model_fields(self):
        all_parking_permits = ParkingPermit.objects.all()
        search_items = [
            {
                "connector": "and",
                "fields": [{"match_type": "iexact", "field_name": "status"}],
                "value": "VALID",
            }
        ]
        qs = apply_filtering(all_parking_permits, search_items)
        self.assertEqual(qs.count(), 1)

        search_items = [
            {
                "connector": "and",
                "fields": [{"match_type": "iexact", "field_name": "status"}],
                "value": "DRAFT",
            }
        ]
        qs = apply_filtering(all_parking_permits, search_items)
        self.assertEqual(qs.count(), 2)

    def test_search_with_related_model_fields(self):
        all_parking_permits = ParkingPermit.objects.all()
        search_items = [
            {
                "connector": "or",
                "fields": [
                    {"match_type": "istartswith", "field_name": "customer__first_name"},
                    {"match_type": "istartswith", "field_name": "customer__last_name"},
                ],
                "value": "last",
            }
        ]
        qs = apply_filtering(all_parking_permits, search_items)
        self.assertEqual(qs.count(), 3)

        search_items = [
            {
                "connector": "or",
                "fields": [
                    {"match_type": "istartswith", "field_name": "customer__first_name"},
                    {"match_type": "istartswith", "field_name": "customer__last_name"},
                ],
                "value": "Firstname A",
            }
        ]
        qs = apply_filtering(all_parking_permits, search_items)
        self.assertEqual(qs.count(), 2)

    def test_search_with_multiple_search_items(self):
        all_parking_permits = ParkingPermit.objects.all()
        search_items = [
            {
                "connector": "or",
                "fields": [
                    {"match_type": "istartswith", "field_name": "customer__first_name"},
                    {"match_type": "istartswith", "field_name": "customer__last_name"},
                ],
                "value": "firstname a",
            },
            {
                "connector": "and",
                "fields": [{"match_type": "iexact", "field_name": "status"}],
                "value": "DRAFT",
            },
        ]
        qs = apply_filtering(all_parking_permits, search_items)
        self.assertEqual(qs.count(), 1)


class DiffMonthsFloorTestCase(TestCase):
    def test_diff_months_floor(self):
        self.assertEqual(diff_months_floor(date(2020, 10, 1), date(2021, 10, 1)), 12)
        self.assertEqual(diff_months_floor(date(2020, 10, 15), date(2021, 10, 1)), 11)
        self.assertEqual(diff_months_floor(date(2021, 9, 1), date(2021, 10, 1)), 1)
        self.assertEqual(diff_months_floor(date(2021, 9, 1), date(2021, 10, 15)), 1)
        self.assertEqual(diff_months_floor(date(2021, 10, 1), date(2021, 10, 15)), 0)
        self.assertEqual(diff_months_floor(date(2021, 10, 15), date(2021, 10, 1)), 0)
        self.assertEqual(diff_months_floor(date(2021, 12, 1), date(2021, 10, 1)), 0)


class DiffMonthsCeilTestCase(TestCase):
    def test_diff_months_ceil(self):
        self.assertEqual(diff_months_ceil(date(2020, 10, 1), date(2021, 10, 1)), 13)
        self.assertEqual(diff_months_ceil(date(2020, 10, 15), date(2021, 10, 1)), 12)
        self.assertEqual(diff_months_ceil(date(2021, 9, 1), date(2021, 10, 1)), 2)
        self.assertEqual(diff_months_ceil(date(2021, 9, 1), date(2021, 10, 15)), 2)
        self.assertEqual(diff_months_ceil(date(2021, 10, 1), date(2021, 10, 15)), 1)
        self.assertEqual(diff_months_ceil(date(2021, 10, 15), date(2021, 10, 1)), 0)
        self.assertEqual(diff_months_ceil(date(2021, 12, 1), date(2021, 10, 1)), 0)


class FindNextDateTestCase(TestCase):
    def test_find_next_date(self):
        self.assertEqual(find_next_date(date(2021, 1, 10), 5), date(2021, 2, 5))
        self.assertEqual(find_next_date(date(2021, 1, 10), 10), date(2021, 1, 10))
        self.assertEqual(find_next_date(date(2021, 1, 10), 20), date(2021, 1, 20))
        self.assertEqual(find_next_date(date(2021, 2, 10), 31), date(2021, 2, 28))
