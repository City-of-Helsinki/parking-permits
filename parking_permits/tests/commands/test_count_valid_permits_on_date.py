import datetime
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from parking_permits.management.commands.count_valid_permits_on_date import (
    count_valid_permits,
)
from parking_permits.models.order import OrderStatus
from parking_permits.models.parking_permit import ParkingPermitStatus
from parking_permits.tests.factories.order import OrderFactory
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory

SAMPLE_DATE = datetime.date(2024, 1, 15)
RANGE_START = datetime.date(2024, 1, 10)
RANGE_END = datetime.date(2024, 1, 20)


def _aware(year, month, day, hour=12):
    return timezone.make_aware(datetime.datetime(year, month, day, hour))


# --- Single date ---------------------------------------------------------


@pytest.mark.django_db()
def test_valid_permit_started_before_date_is_counted():
    ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 6, 1),
    )
    assert count_valid_permits(SAMPLE_DATE) == 1


@pytest.mark.django_db()
def test_valid_permit_started_on_date_is_counted():
    # Any time on the sample date is accepted.
    ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        start_time=_aware(2024, 1, 15, hour=23),
        end_time=_aware(2024, 6, 15),
    )
    assert count_valid_permits(SAMPLE_DATE) == 1


@pytest.mark.django_db()
def test_valid_permit_started_after_sample_date_is_not_counted():
    ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        start_time=_aware(2024, 1, 16),
        end_time=_aware(2024, 6, 16),
    )
    assert count_valid_permits(SAMPLE_DATE) == 0


@pytest.mark.django_db()
def test_valid_permit_ended_before_sample_date_is_not_counted():
    # Guards against a permit still marked VALID (e.g., missed expiration job)
    # whose end_time is before the sample date being counted for that date.
    ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 1, 10),
    )
    assert count_valid_permits(SAMPLE_DATE) == 0


@pytest.mark.django_db()
def test_closed_permit_covering_sample_date_is_counted():
    ParkingPermitFactory(
        status=ParkingPermitStatus.CLOSED,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 2, 1),
    )
    assert count_valid_permits(SAMPLE_DATE) == 1


@pytest.mark.django_db()
def test_closed_permit_ended_before_sample_date_is_not_counted():
    ParkingPermitFactory(
        status=ParkingPermitStatus.CLOSED,
        start_time=_aware(2023, 12, 1),
        end_time=_aware(2024, 1, 10),
    )
    assert count_valid_permits(SAMPLE_DATE) == 0


@pytest.mark.django_db()
def test_closed_permit_started_after_sample_date_is_not_counted():
    ParkingPermitFactory(
        status=ParkingPermitStatus.CLOSED,
        start_time=_aware(2024, 1, 20),
        end_time=_aware(2024, 3, 1),
    )
    assert count_valid_permits(SAMPLE_DATE) == 0


@pytest.mark.django_db()
def test_cancelled_permit_with_paid_order_is_counted():
    order = OrderFactory(status=OrderStatus.CONFIRMED, paid_time=_aware(2024, 1, 10))
    ParkingPermitFactory(
        status=ParkingPermitStatus.CANCELLED,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 2, 1),
        orders=[order],
    )
    assert count_valid_permits(SAMPLE_DATE) == 1


@pytest.mark.django_db()
def test_cancelled_permit_paid_then_order_cancelled_is_still_counted():
    # Regression guard: ending/refunding flips the paid order to CANCELLED but
    # keeps paid_time, so the permit must still count.
    order = OrderFactory(status=OrderStatus.CANCELLED, paid_time=_aware(2024, 1, 10))
    ParkingPermitFactory(
        status=ParkingPermitStatus.CANCELLED,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 2, 1),
        orders=[order],
    )
    assert count_valid_permits(SAMPLE_DATE) == 1


@pytest.mark.django_db()
def test_cancelled_permit_never_paid_is_not_counted_by_default():
    order = OrderFactory(status=OrderStatus.CANCELLED, paid_time=None)
    ParkingPermitFactory(
        status=ParkingPermitStatus.CANCELLED,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 2, 1),
        orders=[order],
    )
    assert count_valid_permits(SAMPLE_DATE) == 0


@pytest.mark.django_db()
def test_cancelled_permit_never_paid_is_counted_when_flag_set():
    order = OrderFactory(status=OrderStatus.CANCELLED, paid_time=None)
    ParkingPermitFactory(
        status=ParkingPermitStatus.CANCELLED,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 2, 1),
        orders=[order],
    )
    assert count_valid_permits(SAMPLE_DATE, include_unpaid_cancelled=True) == 1


@pytest.mark.django_db()
def test_cancelled_permit_paid_after_date_is_not_counted():
    order = OrderFactory(status=OrderStatus.CONFIRMED, paid_time=_aware(2024, 1, 20))
    ParkingPermitFactory(
        status=ParkingPermitStatus.CANCELLED,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 2, 1),
        orders=[order],
    )
    assert count_valid_permits(SAMPLE_DATE) == 0


@pytest.mark.django_db()
def test_cancelled_permit_with_multiple_paid_orders_counted_once():
    first_order = OrderFactory(
        status=OrderStatus.CONFIRMED, paid_time=_aware(2024, 1, 5)
    )
    second_order = OrderFactory(
        status=OrderStatus.CANCELLED, paid_time=_aware(2024, 1, 8)
    )
    ParkingPermitFactory(
        status=ParkingPermitStatus.CANCELLED,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 2, 1),
        orders=[first_order, second_order],
    )
    assert count_valid_permits(SAMPLE_DATE) == 1


@pytest.mark.django_db()
def test_draft_and_payment_in_progress_permits_are_ignored():
    ParkingPermitFactory(
        status=ParkingPermitStatus.DRAFT, start_time=_aware(2024, 1, 1)
    )
    ParkingPermitFactory(
        status=ParkingPermitStatus.PAYMENT_IN_PROGRESS, start_time=_aware(2024, 1, 1)
    )
    assert count_valid_permits(SAMPLE_DATE) == 0


@pytest.mark.django_db()
def test_mixed_population_total():
    # Counted: VALID and started before the sample date.
    ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 6, 1),
    )
    # Counted: CLOSED but its validity window covers the sample date.
    ParkingPermitFactory(
        status=ParkingPermitStatus.CLOSED,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 2, 1),
    )
    # Counted: CANCELLED but was actually paid, so it was genuinely valid.
    paid_order = OrderFactory(
        status=OrderStatus.CANCELLED, paid_time=_aware(2024, 1, 10)
    )
    ParkingPermitFactory(
        status=ParkingPermitStatus.CANCELLED,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 2, 1),
        orders=[paid_order],
    )
    # Not counted: CANCELLED and never paid (timed-out purchase).
    unpaid_order = OrderFactory(status=OrderStatus.CANCELLED, paid_time=None)
    ParkingPermitFactory(
        status=ParkingPermitStatus.CANCELLED,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 2, 1),
        orders=[unpaid_order],
    )
    assert count_valid_permits(SAMPLE_DATE) == 3


# --- Date range ----------------------------------------------------------


@pytest.mark.django_db()
def test_range_counts_permit_valid_only_at_range_start():
    ParkingPermitFactory(
        status=ParkingPermitStatus.CLOSED,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 1, 10, hour=6),
    )
    assert count_valid_permits(RANGE_START, RANGE_END) == 1


@pytest.mark.django_db()
def test_range_counts_permit_valid_only_at_range_end():
    ParkingPermitFactory(
        status=ParkingPermitStatus.CLOSED,
        start_time=_aware(2024, 1, 20, hour=18),
        end_time=_aware(2024, 2, 1),
    )
    assert count_valid_permits(RANGE_START, RANGE_END) == 1


@pytest.mark.django_db()
def test_range_ignores_permit_ended_before_range():
    ParkingPermitFactory(
        status=ParkingPermitStatus.CLOSED,
        start_time=_aware(2023, 12, 1),
        end_time=_aware(2024, 1, 9),
    )
    assert count_valid_permits(RANGE_START, RANGE_END) == 0


@pytest.mark.django_db()
def test_range_ignores_permit_started_after_range():
    ParkingPermitFactory(
        status=ParkingPermitStatus.CLOSED,
        start_time=_aware(2024, 1, 21),
        end_time=_aware(2024, 2, 1),
    )
    assert count_valid_permits(RANGE_START, RANGE_END) == 0


@pytest.mark.django_db()
def test_range_counts_permit_spanning_whole_range_once():
    ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        start_time=_aware(2023, 12, 1),
        end_time=_aware(2024, 6, 1),
    )
    assert count_valid_permits(RANGE_START, RANGE_END) == 1


@pytest.mark.django_db()
def test_range_excludes_never_paid_cancelled_by_default():
    order = OrderFactory(status=OrderStatus.CANCELLED, paid_time=None)
    ParkingPermitFactory(
        status=ParkingPermitStatus.CANCELLED,
        start_time=_aware(2024, 1, 12),
        end_time=_aware(2024, 1, 18),
        orders=[order],
    )
    assert count_valid_permits(RANGE_START, RANGE_END) == 0


# --- Command interface ---------------------------------------------------


@pytest.mark.django_db()
def test_command_prints_total_for_single_date():
    ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 6, 1),
    )
    out = StringIO()
    call_command("count_valid_permits_on_date", "2024-01-15", stdout=out)
    output = out.getvalue().strip()
    assert output == "Best-effort valid permit count for 2024-01-15: 1"


@pytest.mark.django_db()
def test_command_prints_total_for_range():
    ParkingPermitFactory(
        status=ParkingPermitStatus.VALID,
        start_time=_aware(2024, 1, 1),
        end_time=_aware(2024, 6, 1),
    )
    out = StringIO()
    call_command("count_valid_permits_on_date", "2024-01-10", "2024-01-20", stdout=out)
    output = out.getvalue().strip()
    assert output == "Best-effort valid permit count for 2024-01-10..2024-01-20: 1"


@pytest.mark.django_db()
def test_command_raises_on_end_before_start():
    with pytest.raises(CommandError) as exc_info:
        call_command("count_valid_permits_on_date", "2024-01-20", "2024-01-10")
    assert str(exc_info.value) == "end_date must not be earlier than start_date."
