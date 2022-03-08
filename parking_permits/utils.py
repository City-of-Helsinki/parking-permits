import calendar
import operator
from functools import reduce

from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.utils import timezone
from pytz import utc


def apply_ordering(queryset, order_by):
    fields = order_by["order_fields"]
    direction = order_by["order_direction"]
    if direction == "DESC":
        fields = [f"-{field}" for field in fields]
    return queryset.order_by(*fields)


def apply_filtering(queryset, search_items):
    query = Q()
    for search_item in search_items:
        match_type = search_item["match_type"]
        fields = search_item["fields"]
        value = search_item["value"]
        search_item_query = reduce(
            operator.or_, [Q(**{f"{field}__{match_type}": value}) for field in fields]
        )
        query &= search_item_query
    return queryset.filter(query)


def diff_months_floor(start_date, end_date):
    if start_date > end_date:
        return 0
    diff = relativedelta(end_date, start_date)
    return diff.months + diff.years * 12


def diff_months_ceil(start_date, end_date):
    if start_date > end_date:
        return 0
    diff = relativedelta(end_date, start_date)
    diff_months = diff.months + diff.years * 12
    if diff.days >= 0:
        diff_months += 1
    return diff_months


def get_end_time(start_time, diff_months):
    end_time = start_time + relativedelta(months=diff_months, days=-1)
    return timezone.make_aware(
        end_time.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=None)
    )


def find_next_date(dt, day):
    """
    Find the next date with specific day number after given date.
    If the day number of given date matches the day, the original
    date will be returned.

    Args:
        dt (datetime.date): the starting date to search for
        day (int): the day number of found date

    Returns:
        datetime.date: the found date
    """
    try:
        found = dt.replace(day=day)
    except ValueError:
        _, month_end = calendar.monthrange(dt.year, dt.month)
        found = dt.replace(day=month_end)
    if found < dt:
        found += relativedelta(months=1)
    return found


def date_time_to_utc(dt):
    return (
        dt.replace(microsecond=0).astimezone(utc).replace(tzinfo=None).isoformat() + "Z"
    )
