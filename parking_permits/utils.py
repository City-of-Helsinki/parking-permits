import calendar
import copy
import zoneinfo
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime
from decimal import ROUND_UP, Decimal
from itertools import chain

from ariadne import convert_camel_case_to_snake
from dateutil.relativedelta import relativedelta
from django.db import models
from django.utils import timezone as tz
from graphql import GraphQLResolveInfo
from pytz import utc

HELSINKI_TZ = zoneinfo.ZoneInfo("Europe/Helsinki")


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
    end_time = start_time + relativedelta(months=diff_months, days=-1)
    return tz.make_aware(
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
        if index == product_count:
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


def round_up(v):
    return (
        "{:0.2f}".format(Decimal(v).quantize(Decimal(".001"), rounding=ROUND_UP))
        if v
        else "0.00"
    )
