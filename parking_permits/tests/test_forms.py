from django.test import TestCase
from django.utils import timezone

from parking_permits.forms import OrderSearchForm, PdfExportForm
from parking_permits.tests.factories.order import OrderFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory


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


class OrderSearchFormDateRangeTestCase(TestCase):
    def run_date_range_sub_tests(self, order, form_data, sub_tests):
        """Utility function for running a suite of subtests specifically for the date range search.

        Creates a single parking permit with a start and an optional end time, assigns it to the given order,
        and then asserts the result count."""
        form = OrderSearchForm(form_data)
        self.assertTrue(form.is_valid())

        for sub_test in sub_tests:
            permit_args = sub_test["permit"]
            start_time = timezone.datetime(
                *permit_args["start_time"], tzinfo=timezone.utc
            )
            # Set end_time only if its arguments exist in the subtest data.
            end_time = (
                timezone.datetime(*args, tzinfo=timezone.utc)
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
