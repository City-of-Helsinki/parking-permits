from datetime import date

import pytest
from django.test import TestCase

from parking_permits.models import Vehicle
from parking_permits.tests.factories.vehicle import VehicleFactory
from parking_permits.utils import (
    ModelDiffer,
    diff_months_ceil,
    diff_months_floor,
    find_next_date,
    flatten_dict,
    get_model_diff,
)


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


@pytest.mark.django_db
def test_get_model_diff():
    vehicle1 = VehicleFactory(registration_number="ABC-123", model="Model")
    vehicle2 = Vehicle.objects.get(id=vehicle1.id)
    vehicle2.pk = None
    vehicle2.registration_number = "FOO-321"
    vehicle2.model = "Some other model"
    vehicle2.save()

    diff = get_model_diff(vehicle1, vehicle2, fields=["registration_number"])

    assert len(diff.keys()) == 1
    assert "registration_number" in diff
    assert diff["registration_number"] == ("ABC-123", "FOO-321")


def test_flatten_dict():
    d = dict(
        value=1,
        nested=dict(value=2, nested=dict(value=3)),
        foo="bar",
        other_nested=dict(value=4, foo=["a", "list"]),
    )
    assert flatten_dict(d) == {
        "value": 1,
        "nested__value": 2,
        "nested__nested__value": 3,
        "foo": "bar",
        "other_nested__value": 4,
        "other_nested__foo": ["a", "list"],
    }
    assert flatten_dict(d, separator="/") == {
        "value": 1,
        "nested/value": 2,
        "nested/nested/value": 3,
        "foo": "bar",
        "other_nested/value": 4,
        "other_nested/foo": ["a", "list"],
    }


@pytest.mark.django_db
def test_model_differ():
    vehicle: Vehicle = VehicleFactory(registration_number="ABC-123", model="Model")

    diff = ModelDiffer.start(vehicle, fields=["registration_number"])
    vehicle.registration_number = "FOO-321"
    vehicle.model = "Some other model"
    diff_dict = diff.stop()
    vehicle.registration_number = "BAR-777"
    print(diff_dict)
    assert len(diff_dict.keys()) == 1
    assert "registration_number" in diff_dict
    assert diff_dict["registration_number"] == ("ABC-123", "FOO-321")


@pytest.mark.django_db
def test_model_differ_as_context_manager():
    vehicle: Vehicle = VehicleFactory(registration_number="ABC-123", model="Model")

    with ModelDiffer(vehicle, fields=["registration_number"]) as diff_dict:
        vehicle.registration_number = "FOO-321"
        vehicle.model = "Some other model"

    vehicle.registration_number = "BAR-777"

    assert len(diff_dict.keys()) == 1
    assert "registration_number" in diff_dict
    assert diff_dict["registration_number"] == ("ABC-123", "FOO-321")
