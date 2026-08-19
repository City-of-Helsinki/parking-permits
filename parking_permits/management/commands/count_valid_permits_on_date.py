import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from parking_permits.models.parking_permit import ParkingPermit, ParkingPermitStatus


def _range_bounds(start_date, end_date):
    current_timezone = timezone.get_current_timezone()
    range_start = timezone.make_aware(
        datetime.datetime.combine(start_date, datetime.time.min), current_timezone
    )
    range_end = timezone.make_aware(
        datetime.datetime.combine(end_date, datetime.time.max), current_timezone
    )
    return range_start, range_end


def count_valid_permits(start_date, end_date=None, *, include_unpaid_cancelled=False):
    """Best-effort count of permits that were valid on any date in the given
    inclusive range. With a single date, counts permits valid on that date.

    There is no historical status log, so validity is inferred from the
    permits' current status together with their start/end times and, for
    cancelled permits, whether they were ever actually paid.
    """
    if end_date is None:
        end_date = start_date

    range_start, range_end = _range_bounds(start_date, end_date)

    # Currently VALID permits that started on or before the end of the range
    # and whose (historically optional) end_time overlaps the range. If a
    # permit is still marked VALID but has an end_time before range_start
    # (e.g., expiration job missed), it would be incorrectly counted for
    # historical periods.
    valid_permits = ParkingPermit.objects.filter(
        status=ParkingPermitStatus.VALID,
        start_time__lte=range_end,
    ).filter(Q(end_time__isnull=True) | Q(end_time__gte=range_start))

    # Permits that have since been CLOSED or CANCELLED but whose validity
    # window [start_time, end_time] overlaps the range.
    ended_permits = ParkingPermit.objects.filter(
        status__in=(ParkingPermitStatus.CLOSED, ParkingPermitStatus.CANCELLED),
        start_time__lte=range_end,
    ).filter(Q(end_time__isnull=True) | Q(end_time__gte=range_start))

    if not include_unpaid_cancelled:
        # A genuinely valid-then-cancelled permit always has at least one order
        # that was paid on or before the end of the range. `paid_time` is set
        # when an order is confirmed/paid and is never cleared, so it stays
        # reliable even when the order is later moved to CANCELLED on ending or
        # refund. Timed-out purchases never receive a `paid_time`.
        ended_permits = ended_permits.filter(
            Q(status=ParkingPermitStatus.CLOSED)
            | Q(
                status=ParkingPermitStatus.CANCELLED,
                orders__paid_time__isnull=False,
                orders__paid_time__lte=range_end,
            )
        )

    # Note that the two querysets filter for different statuses, so
    # there is no risk of overlap and we can just add the counts
    # without worrying about double-counting.
    return valid_permits.distinct("id").count() + ended_permits.distinct("id").count()


class Command(BaseCommand):
    help = (
        "Calculate a best-effort count of parking permits that were valid on a "
        "given past date, or on any date within an inclusive date range. "
        "Intended for dates that predate the daily permit count snapshots."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "start_date",
            type=datetime.date.fromisoformat,
            help="Date (or range start) in ISO format (YYYY-MM-DD).",
        )
        parser.add_argument(
            "end_date",
            type=datetime.date.fromisoformat,
            nargs="?",
            help="Optional inclusive range end in ISO format (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--include-unpaid-cancelled",
            action="store_true",
            help=(
                "Include CANCELLED permits that were never paid for. These are "
                "excluded by default, since they are most likely purchases that "
                "timed out and were never actually valid."
            ),
        )

    def handle(self, *args, **options):
        start_date = options["start_date"]
        end_date = options["end_date"] or start_date

        if end_date < start_date:
            raise CommandError("end_date must not be earlier than start_date.")

        total = count_valid_permits(
            start_date,
            end_date,
            include_unpaid_cancelled=options["include_unpaid_cancelled"],
        )

        if start_date == end_date:
            period = start_date.isoformat()
        else:
            period = f"{start_date.isoformat()}..{end_date.isoformat()}"

        self.stdout.write(
            self.style.SUCCESS(f"Best-effort valid permit count for {period}: {total}")
        )
