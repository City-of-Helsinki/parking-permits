import zoneinfo
from datetime import date, datetime
from decimal import Decimal

import pytest
from django.test import TestCase

from parking_permits.models import Vehicle
from parking_permits.tests.factories.vehicle import VehicleFactory
from parking_permits.utils import (
    ModelDiffer,
    calc_net_price,
    calc_vat_price,
    date_time_to_helsinki,
    diff_months_ceil,
    diff_months_floor,
    find_next_date,
    flatten_dict,
    get_last_day_of_month,
    get_model_diff,
    increment_end_time,
)


def test_increment_end_time_during_month():
    assert increment_end_time(
        start_time=datetime(
            2023,
            5,
            16,
            12,
            00,
            00,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
        end_time=datetime(
            2023,
            6,
            15,
            23,
            59,
            59,
            999999,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
    ) == datetime(
        2023, 7, 15, 23, 59, 59, 999999, tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki")
    )

    assert increment_end_time(
        start_time=datetime(
            2023,
            12,
            21,
            12,
            00,
            00,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
        end_time=datetime(
            2024,
            1,
            20,
            23,
            59,
            59,
            999999,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
    ) == datetime(
        2024, 2, 20, 23, 59, 59, 999999, tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki")
    )
    assert increment_end_time(
        start_time=datetime(
            2023,
            6,
            11,
            12,
            00,
            00,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
        end_time=datetime(
            2023,
            6,
            10,
            23,
            59,
            59,
            999999,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
    ) == datetime(
        2023, 7, 10, 23, 59, 59, 999999, tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki")
    )


def test_increment_end_time_dec_to_march():
    assert increment_end_time(
        start_time=datetime(
            2023,
            1,
            31,
            12,
            00,
            00,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
        end_time=datetime(
            2023,
            2,
            28,
            23,
            59,
            59,
            999999,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
    ) == datetime(
        2023, 3, 30, 23, 59, 59, 999999, tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki")
    )


def test_increment_end_time_jan_to_feb():
    assert increment_end_time(
        start_time=datetime(
            2023,
            1,
            1,
            12,
            00,
            00,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
        end_time=datetime(
            2023,
            1,
            31,
            23,
            59,
            59,
            999999,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
    ) == datetime(
        2023, 2, 28, 23, 59, 59, 999999, tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki")
    )
    # leap year
    assert increment_end_time(
        start_time=datetime(
            2024,
            1,
            1,
            12,
            00,
            00,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
        end_time=datetime(
            2024,
            1,
            31,
            23,
            59,
            59,
            999999,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
    ) == datetime(
        2024, 2, 29, 23, 59, 59, 999999, tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki")
    )


def test_increment_end_time_july_to_aug():
    assert increment_end_time(
        start_time=datetime(
            2024,
            7,
            1,
            12,
            00,
            00,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
        end_time=datetime(
            2024,
            7,
            31,
            23,
            59,
            59,
            999999,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
    ) == datetime(
        2024, 8, 31, 23, 59, 59, 999999, tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki")
    )


def test_increment_end_time_may_to_june():
    assert increment_end_time(
        start_time=datetime(
            2024,
            5,
            1,
            12,
            00,
            00,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
        end_time=datetime(
            2024,
            5,
            31,
            23,
            59,
            59,
            999999,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
    ) == datetime(
        2024, 6, 30, 23, 59, 59, 999999, tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki")
    )


def test_increment_end_time_jan_to_march():
    assert increment_end_time(
        start_time=datetime(
            2023,
            1,
            30,
            12,
            00,
            00,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
        end_time=datetime(
            2023,
            2,
            28,
            23,
            59,
            59,
            999999,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
    ) == datetime(
        2023, 3, 29, 23, 59, 59, 999999, tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki")
    )


def test_increment_end_time_june_to_july():
    assert increment_end_time(
        start_time=datetime(
            2024,
            6,
            1,
            12,
            00,
            00,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
        end_time=datetime(
            2024,
            6,
            30,
            23,
            59,
            59,
            999999,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
    ) == datetime(
        2024, 7, 31, 23, 59, 59, 999999, tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki")
    )


def test_increment_end_time_april_to_nov():
    assert increment_end_time(
        start_time=datetime(
            2023,
            4,
            1,
            12,
            00,
            00,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
        end_time=datetime(
            2024,
            10,
            31,
            23,
            59,
            59,
            999999,
            tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
        ),
    ) == datetime(
        2024,
        11,
        30,
        23,
        59,
        59,
        999999,
        tzinfo=zoneinfo.ZoneInfo(key="Europe/Helsinki"),
    )


def test_get_last_day_of_month():
    assert get_last_day_of_month(datetime(2024, 1, 2, 12, 12, 00)) == 31
    assert get_last_day_of_month(datetime(2023, 2, 2, 12, 12, 00)) == 28
    assert get_last_day_of_month(datetime(2024, 3, 2, 12, 12, 00)) == 31
    assert get_last_day_of_month(datetime(2024, 4, 2, 12, 12, 00)) == 30
    assert get_last_day_of_month(datetime(2024, 5, 2, 12, 12, 00)) == 31
    assert get_last_day_of_month(datetime(2024, 6, 2, 12, 12, 00)) == 30
    assert get_last_day_of_month(datetime(2024, 7, 2, 12, 12, 00)) == 31
    assert get_last_day_of_month(datetime(2024, 8, 2, 12, 12, 00)) == 31
    assert get_last_day_of_month(datetime(2024, 9, 2, 12, 12, 00)) == 30
    assert get_last_day_of_month(datetime(2024, 10, 2, 12, 12, 00)) == 31
    assert get_last_day_of_month(datetime(2024, 11, 2, 12, 12, 00)) == 30
    assert get_last_day_of_month(datetime(2024, 12, 2, 12, 12, 00)) == 31

    # leap year
    assert get_last_day_of_month(datetime(2024, 2, 2, 12, 12, 00)) == 29

    for i in range(1, 31):
        assert get_last_day_of_month(datetime(2024, 5, i, 12, 12, 00)) == 31

    for i in range(1, 30):
        assert get_last_day_of_month(datetime(2024, 4, i, 12, 12, 00)) == 30

    for i in range(1, 28):
        assert get_last_day_of_month(datetime(2023, 2, i, 12, 12, 00)) == 28


@pytest.mark.parametrize(
    "gross_price,vat,net_price,vat_price",
    [
        pytest.param(100, 0.255, 79.68, 20.32, id="VAT 25.5%"),
        pytest.param(100, 0.24, 80.65, 19.36, id="VAT 24%"),
        pytest.param(100, None, 0, 0, id="VAT none"),
        pytest.param(None, 0.255, 0, 0, id="gross none"),
    ],
)
def test_calc_prices(gross_price, vat, net_price, vat_price):
    delta = Decimal(0.01)
    assert calc_net_price(gross_price, vat) == pytest.approx(Decimal(net_price), delta)
    assert calc_vat_price(gross_price, vat) == pytest.approx(Decimal(vat_price), delta)


class DateTimeToHelsinkiTestCase(TestCase):
    def test_date_time_to_helsinki(self):
        dt = datetime(2023, 10, 25, 10, 30, tzinfo=zoneinfo.ZoneInfo("UTC"))
        hel_tz = date_time_to_helsinki(dt)
        self.assertEqual(hel_tz, "2023-10-25T13:30:00")


class DiffMonthsFloorTestCase(TestCase):
    def test_diff_months_floor(self):
        self.assertEqual(diff_months_floor(date(2020, 10, 1), date(2021, 10, 1)), 12)
        self.assertEqual(diff_months_floor(date(2020, 10, 15), date(2021, 10, 1)), 11)
        self.assertEqual(diff_months_floor(date(2021, 9, 1), date(2021, 10, 1)), 1)
        self.assertEqual(diff_months_floor(date(2021, 9, 1), date(2021, 10, 15)), 1)
        self.assertEqual(diff_months_floor(date(2021, 10, 1), date(2021, 10, 15)), 0)
        self.assertEqual(diff_months_floor(date(2021, 10, 15), date(2021, 10, 1)), 0)
        self.assertEqual(diff_months_floor(date(2021, 12, 1), date(2021, 10, 1)), 0)
        self.assertEqual(diff_months_floor(date(2021, 1, 1), date(2021, 1, 1)), 0)
        self.assertEqual(diff_months_floor(date(2024, 1, 31), date(2024, 2, 29)), 1)
        self.assertEqual(diff_months_floor(date(2024, 1, 31), date(2024, 3, 1)), 1)
        self.assertEqual(diff_months_floor(date(2024, 1, 31), date(2024, 2, 28)), 0)
        self.assertEqual(diff_months_floor(date(2025, 1, 31), date(2025, 2, 28)), 1)
        self.assertEqual(diff_months_floor(date(2025, 1, 30), date(2025, 2, 28)), 1)
        self.assertEqual(diff_months_floor(date(2025, 1, 29), date(2025, 2, 28)), 1)
        self.assertEqual(diff_months_floor(date(2025, 1, 28), date(2025, 2, 28)), 1)
        self.assertEqual(diff_months_floor(date(2025, 1, 27), date(2025, 2, 28)), 1)
        self.assertEqual(diff_months_floor(date(2025, 2, 1), date(2025, 2, 28)), 0)
        self.assertEqual(diff_months_floor(date(2025, 2, 1), date(2025, 3, 1)), 1)


class DiffMonthsCeilTestCase(TestCase):
    def test_diff_months_ceil(self):
        self.assertEqual(diff_months_ceil(date(2020, 10, 1), date(2021, 10, 1)), 13)
        self.assertEqual(diff_months_ceil(date(2020, 10, 15), date(2021, 10, 1)), 12)
        self.assertEqual(diff_months_ceil(date(2021, 9, 1), date(2021, 10, 1)), 2)
        self.assertEqual(diff_months_ceil(date(2021, 9, 1), date(2021, 10, 15)), 2)
        self.assertEqual(diff_months_ceil(date(2021, 10, 1), date(2021, 10, 15)), 1)
        self.assertEqual(diff_months_ceil(date(2021, 10, 15), date(2021, 10, 1)), 0)
        self.assertEqual(diff_months_ceil(date(2021, 12, 1), date(2021, 10, 1)), 0)
        self.assertEqual(diff_months_ceil(date(2021, 1, 1), date(2021, 1, 1)), 1)


class FindNextDateTestCase(TestCase):
    def test_find_next_date(self):
        self.assertEqual(find_next_date(date(2021, 1, 10), 5), date(2021, 1, 31))
        self.assertEqual(find_next_date(date(2021, 1, 10), 10), date(2021, 1, 10))
        self.assertEqual(find_next_date(date(2021, 1, 10), 20), date(2021, 1, 20))
        self.assertEqual(find_next_date(date(2021, 2, 10), 31), date(2021, 2, 28))
        self.assertEqual(find_next_date(date(2024, 9, 1), 28), date(2024, 9, 28))
        self.assertEqual(find_next_date(date(2024, 11, 27), 31), date(2024, 11, 30))


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
