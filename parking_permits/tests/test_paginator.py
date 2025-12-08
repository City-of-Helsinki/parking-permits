from django.test import TestCase

from parking_permits.models import ParkingPermit
from parking_permits.paginator import QuerySetPaginator
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory


class QuerySetPaginatorTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        for _i in range(10):
            ParkingPermitFactory()

    def test_paginator_with_default_page_size(self):
        qs = ParkingPermit.objects.all()
        page_input = {"page": 1}
        paginator = QuerySetPaginator(qs, page_input)
        self.assertEqual(paginator.object_list.count(), 10)
        expected_page_info = {
            "num_pages": 1,
            "next": None,
            "prev": None,
            "page": 1,
            "start_index": 1,
            "end_index": 10,
            "count": 10,
        }
        self.assertEqual(paginator.page_info, expected_page_info)

    def test_paginator_with_custom_page_size(self):
        qs = ParkingPermit.objects.all()
        page_input = {"page": 2, "page_size": 3}
        paginator = QuerySetPaginator(qs, page_input)
        self.assertEqual(paginator.object_list.count(), 3)
        expected_page_info = {
            "num_pages": 4,
            "next": 3,
            "prev": 1,
            "page": 2,
            "start_index": 4,
            "end_index": 6,
            "count": 10,
        }
        self.assertEqual(paginator.page_info, expected_page_info)
