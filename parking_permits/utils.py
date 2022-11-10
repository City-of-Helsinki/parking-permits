import calendar
from collections import OrderedDict
from collections.abc import Callable
from itertools import chain

from ariadne import convert_camel_case_to_snake
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from graphql import GraphQLResolveInfo
from pytz import utc


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
    zone,
    is_low_emission,
    is_secondary,
    permit_start_date,
    permit_end_date,
):
    products = zone.products.for_resident().for_date_range(
        permit_start_date,
        permit_end_date,
    )
    permit_prices = []
    for product in products:
        start_date = max(product.start_date, permit_start_date)
        end_date = min(product.end_date, permit_end_date)
        quantity = diff_months_ceil(start_date, end_date)
        permit_prices.append(
            {
                "original_unit_price": product.unit_price,
                "unit_price": product.get_modified_unit_price(
                    is_low_emission, is_secondary
                ),
                "start_date": start_date,
                "end_date": end_date,
                "quantity": quantity,
            }
        )
    return permit_prices


def get_meta_value(meta_pair_list, meta_pair_key):
    return next(
        (
            meta_pair.get("value")
            for meta_pair in meta_pair_list
            if meta_pair.get("key") == meta_pair_key
        ),
        None,
    )


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
