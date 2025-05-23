import calendar
import copy
import zoneinfo
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import ROUND_UP, Decimal
from itertools import chain
from typing import Any, Iterable, Iterator, Optional, Union

from ariadne import convert_camel_case_to_snake
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import models
from django.utils import timezone as tz
from graphql import GraphQLResolveInfo
from pytz import utc

HELSINKI_TZ = zoneinfo.ZoneInfo("Europe/Helsinki")

PERMIT_END_TIME_SHIFT_TOLERANCE = relativedelta(days=5)

Currency = Optional[Union[str, float, Decimal]]


# forward-compatible implementation of itertools.pairwise() from py3.10
# https://docs.python.org/3/library/itertools.html#itertools.pairwise
def pairwise(iterable: Iterable) -> Iterator[tuple[Any, Any]]:
    # pairwise('ABCDEFG') → AB BC CD DE EF FG
    iterator = iter(iterable)
    a = next(iterator, None)
    for b in iterator:
        yield a, b
        a = b


class DefaultOrderedDict(OrderedDict):
    def __init__(self, default_factory=None, *a, **kw):
        if default_factory is not None and not isinstance(default_factory, Callable):
            raise TypeError("first argument must be callable")
        OrderedDict.__init__(self, *a, **kw)
        self.default_factory = default_factory

    def __getitem__(self, key):
        try:
            return OrderedDict.__getitem__(self, key)
        except KeyError:
            return self.__missing__(key)

    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = value = self.default_factory()
        return value

    def __reduce__(self):
        if self.default_factory is None:
            args = tuple()
        else:
            args = (self.default_factory,)
        return type(self), args, None, None, self.items()

    def copy(self):
        return self.__copy__()

    def __copy__(self):
        return type(self)(self.default_factory, self)

    def __deepcopy__(self, memo):
        import copy

        return type(self)(self.default_factory, copy.deepcopy(self.items()))

    def __repr__(self):
        return "OrderedDefaultDict(%s, %s)" % (
            self.default_factory,
            OrderedDict.__repr__(self),
        )


def safe_cast(val, to_type, default=None):
    try:
        return to_type(val)
    except (ValueError, TypeError):
        return default


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


def start_date_to_datetime(date):
    return datetime.combine(date, datetime.min.time(), tzinfo=HELSINKI_TZ)


def end_date_to_datetime(date):
    return datetime.combine(date, datetime.max.time(), tzinfo=HELSINKI_TZ)


def get_end_time(start_time, diff_months):
    """Adds number of months equal to `diff_months` to `start_time`.

    The final result should be 23:59 on the previous day for example:

    Current date: 25th Oct
    Final result (+1 month): 24 Nov 23:59 EET

    Result will be in default timezone (i.e. TIME_ZONE).
    """

    # normalize start time to midnight localtime
    start_time = start_time.astimezone(tz.get_default_timezone())
    start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)

    # add 1 month minus one day
    end_time = start_time + relativedelta(months=diff_months, days=-1)

    return normalize_end_time(end_time)


def get_last_day_of_month(date: datetime):
    next_month = date.replace(day=28) + timedelta(days=4)
    return (next_month - timedelta(days=next_month.day)).day


def increment_end_time(start_time, end_time, months=1):
    """
    Calculate the end time by adding `months` to the start time.
    """
    month_diff = diff_months_floor(
        start_time, end_time + PERMIT_END_TIME_SHIFT_TOLERANCE
    )
    return get_end_time(start_time, month_diff + months)


def normalize_end_time(end_time):
    """Should ensure that the end time is always 23:59 of that day,
    accounting for DST."""
    return tz.make_aware(
        end_time.replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=999999,
            tzinfo=None,
        )
    )


def find_next_date(dt, day):
    """
    Find the next date with specific day number after given date.
    If the day number of given date matches the day, the original
    date will be returned.

    If the next date would be in the following month, last day
    of current month is returned.

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
        _, month_end = calendar.monthrange(dt.year, dt.month)
        found = found.replace(day=month_end)
    return found


def date_time_to_utc(dt):
    return (
        dt.replace(microsecond=0).astimezone(utc).replace(tzinfo=None).isoformat() + "Z"
    )


def date_time_to_helsinki(dt):
    return (
        dt.replace(microsecond=0)
        .astimezone(HELSINKI_TZ)
        .replace(tzinfo=None)
        .isoformat()
    )


def format_local_time(dt):
    return (
        tz.localtime(dt).replace(microsecond=0).replace(tzinfo=None).isoformat() + "Z"
    )


def convert_to_snake_case(d):
    if isinstance(d, str):
        return convert_camel_case_to_snake(d)
    if isinstance(d, list):
        return [convert_to_snake_case(i) if isinstance(i, dict) else i for i in d]
    if isinstance(d, dict):
        converted = {}
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                v = convert_to_snake_case(v)
            converted[convert_camel_case_to_snake(k)] = v
        return converted
    return d


def get_permit_prices(
    parking_zone,
    is_low_emission_vehicle,
    is_secondary_permit,
    permit_start_date,
    permit_end_date,
):
    products = parking_zone.products.for_resident().for_date_range(
        permit_start_date,
        permit_end_date,
    )

    permit_prices = []
    product_count = len(products) if len(products) > 1 else 0
    for index, product in enumerate(products, start=1):
        start_date = max(product.start_date, permit_start_date)
        end_date = min(product.end_date, permit_end_date)
        quantity = diff_months_ceil(start_date, end_date)
        #  remove one month from the last product if there are multiple products
        #  and the start date is not first day of the month
        if index == product_count and permit_start_date.day != 1:
            quantity -= 1
        permit_prices.append(
            {
                "original_unit_price": product.unit_price,
                "unit_price": product.get_modified_unit_price(
                    is_low_emission_vehicle, is_secondary_permit
                ),
                "start_date": start_date,
                "end_date": end_date,
                "quantity": quantity,
            }
        )
    return permit_prices


def get_meta_item(meta_pair_list, meta_pair_key):
    return next(
        (
            meta_pair
            for meta_pair in meta_pair_list
            if meta_pair.get("key") == meta_pair_key
        ),
        None,
    )


def get_meta_value(meta_pair_list, meta_pair_key):
    item = get_meta_item(meta_pair_list, meta_pair_key)
    return item.get("value") if item else None


def snake_to_camel_dict(dictionary):
    res = dict()
    for key in dictionary.keys():
        if isinstance(dictionary[key], dict):
            res[camel_str(key)] = snake_to_camel_dict(dictionary[key])
        elif isinstance(dictionary[key], list):
            res[camel_str(key)] = [snake_to_camel_dict(val) for val in dictionary[key]]
        else:
            res[camel_str(key)] = dictionary[key]
    return res


def camel_str(snake_str):
    first, *others = snake_str.split("_")
    return "".join([first.lower(), *map(str.title, others)])


def to_dict(instance):
    if not instance:
        return None
    opts = instance._meta
    data = {}
    for f in chain(opts.concrete_fields, opts.private_fields):
        data[f.name] = f.value_from_object(instance)
    for f in opts.many_to_many:
        data[f.name] = [i.id for i in f.value_from_object(instance)]
    return data


def get_user_from_resolver_args(*args, **__):
    try:
        info: GraphQLResolveInfo = args[1]
        return info.context["request"].user
    except (KeyError, AttributeError, IndexError):
        return None


def get_user_from_api_view_method_args(view, request, *_, **__):
    return request.user


def get_model_diff(a: models.Model, b: models.Model, fields: list = None) -> dict:
    if type(a) is not type(b):
        raise TypeError(f"a and b must have the same type ({type(a)} != {type(b)}))")
    if not isinstance(a, models.Model):
        raise TypeError(
            f"Must be an instance of {type(models.Model)} or its subclass (was: {type(a)}"
        )
    difference = dict()
    a_dict = vars(a)
    b_dict = vars(b)
    for field_name in a_dict.keys():
        if field_name == "_state" or (fields and field_name not in fields):
            continue
        a_value = a_dict[field_name]
        b_value = b_dict[field_name]
        if a_value != b_value:
            difference[field_name] = (a_value, b_value)
    return difference


class ModelDiffer:
    def __init__(self, instance: models.Model, fields: list[str] = None):
        # Take a snapshot of the instance.
        self.a = copy.deepcopy(instance)
        # Keep a reference to the instance; will be snapshot in the end.
        self.b = instance
        self.fields = fields
        self._finished = False
        self._result = dict()

    @staticmethod
    def start(obj: models.Model, fields: list[str] = None):
        return ModelDiffer(obj, fields=fields)

    def stop(self):
        if not self._finished:
            # End the diff and take a snapshot of the instance's state.
            self.b = copy.deepcopy(self.b)
            self._finished = True
            self.result.update(self.get_diff(self.a, self.b, fields=self.fields))
        return self.result

    @property
    def result(self):
        return self._result

    def __enter__(self):
        return self.result

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    get_diff = staticmethod(get_model_diff)


def flatten_dict(d, separator="__", prefix="", _output_ref=None) -> dict:
    output = dict() if _output_ref is None else _output_ref
    for k, v in d.items():
        if isinstance(v, dict):
            flatten_dict(
                v,
                separator=separator,
                prefix=f"{prefix}{k}{separator}",
                _output_ref=output,
            )
        else:
            output[f"{prefix}{k}"] = v
    return output


def calc_net_price(gross_price: Currency, vat: Currency) -> Decimal:
    """Returns the net price based on the gross and VAT e.g. 0.255

    Net price is calculated thus:

        gross / (1 + vat)

    For example, gross 100 EUR, VAT 25.5% would be:

        100 / 1.255 = ~79.68

    If gross or vat is zero or None, returns zero.
    """
    return (
        Decimal(gross_price) / Decimal(1 + (Decimal(vat or 0)))
        if gross_price and vat
        else Decimal(0)
    )


def calc_vat_price(gross_price: Currency, vat: Currency) -> Decimal:
    """Returns the VAT price based on the gross and VAT e.g. 0.255

    VAT price is equal to the gross minus the net.

    For example, gross 100 EUR, VAT 25.5% would be net price of ~79.68.

    VAT price would therefore be 100-79.68 = ~20.32
    """
    return (
        Decimal(gross_price) - calc_net_price(gross_price, vat)
        if gross_price and vat
        else Decimal(0)
    )


def quantize(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal(".0001"), rounding=ROUND_UP)


def format_currency(value) -> str:
    return "{:0.2f}".format(value)


def round_up(value) -> str:
    return format_currency(quantize(value))


def is_valid_city(city):
    if settings.HELSINKI_ADDRESS_CHECK:
        return city and city.casefold() == "helsinki"
    return True
