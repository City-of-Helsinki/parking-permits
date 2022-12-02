import dataclasses
import re
import typing
import zoneinfo
from dataclasses import dataclass
from datetime import datetime

from django.core.management import BaseCommand
from django.utils import timezone

from parking_permits.services import kmo

# E.g. 1.1.2011 1:01, 31.12.2012 15:50
PASI_DATETIME_FORMAT = re.compile(
    r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{4})\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})"
)


class Command(BaseCommand):
    help = "Import CSV file exported from Pasi."

    def handle(self, *args, **options):
        pass


def parse_pasi_datetime(timestamp: str):
    match = re.match(PASI_DATETIME_FORMAT, timestamp)

    def group_as_int(name: str):
        return int(match.group(name))

    return timezone.datetime(
        year=group_as_int("year"),
        month=group_as_int("month"),
        day=group_as_int("day"),
        hour=group_as_int("hour"),
        minute=group_as_int("minute"),
        tzinfo=zoneinfo.ZoneInfo("Europe/Helsinki"),
    )


def make_pasi_datetime_property(attr_name):
    def _get_dt_attr(self) -> datetime:
        return getattr(self, attr_name)

    def _set_dt_attr(self, val):
        if isinstance(val, str):
            setattr(self, attr_name, parse_pasi_datetime(val))
        else:
            setattr(self, attr_name, val)

    return property(fget=_get_dt_attr, fset=_set_dt_attr)


@dataclass
class PasiResidentPermit:
    # Mapping from CSV header names to field names.
    # NOTE: Order matters here; in case index-based access is required.
    CSV_HEADER_TO_FIELD = {
        "Tunnuksen asianumero": "id",
        "Tunnuksen tyyppi": None,
        "Voimassaolon alkamispvm": "start_dt",
        "Voimassaolon päättymispvm": "end_dt",
        "Liittyvän henkilön / Yrityksen nimi": None,
        "Hetu": "national_id_number",
        "Osoite": "address_line",
        "Postinumero": None,
        "Postitoimipaikka": None,
        "Alueen osoite": None,
        # It's a plural, but actually contains only a single registration number per row.
        "Rekisterinumerot": "registration_number",
    }

    id: int
    national_id_number: str
    city: str
    registration_number: str
    address_line: str = property(lambda self: self._address_line)
    start_dt: datetime = make_pasi_datetime_property("_start_dt")
    end_dt: datetime = make_pasi_datetime_property("_end_dt")

    _address_line: str = dataclasses.field(init=False, default=None)
    _start_dt: datetime = dataclasses.field(init=False, default=None)
    _end_dt: datetime = dataclasses.field(init=False, default=None)
    _street_name: typing.Optional[str] = dataclasses.field(init=False, default=None)
    _street_number: typing.Optional[str] = dataclasses.field(init=False, default=None)

    @address_line.setter
    def address_line(self, val):
        self._address_line = val
        self._street_name, self._street_number = kmo.parse_street_name_and_number(
            self.address_line
        )

    @property
    def language(self):
        if self.city.upper() == "HELSINGFORS":
            return "sv"
        return "fi"

    @property
    def street_name(self):
        return self._street_name

    @property
    def street_number(self):
        return self._street_number
