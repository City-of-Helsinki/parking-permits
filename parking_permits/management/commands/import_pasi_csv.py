import csv
import dataclasses
import re
import zoneinfo
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, NoReturn, Optional

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management import BaseCommand
from django.utils import timezone

from parking_permits.models import Address, Customer, ParkingPermit, Vehicle
from parking_permits.services import dvv, kmo
from parking_permits.services.traficom import Traficom

# E.g. 1.1.2011 1:01, 31.12.2012 15:50
PASI_DATETIME_FORMAT = re.compile(
    r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{4})\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})"
)


class PasiImportError(Exception):
    pass


class PasiValidationError(PasiImportError):
    pass


class PasiPermitExists(PasiImportError):
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
    _street_name: Optional[str] = dataclasses.field(init=False, default=None)
    _street_number: Optional[str] = dataclasses.field(init=False, default=None)

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


class PasiCsvReader:
    HEADER_FIELD_MAPPING = {
        "Tunnuksen asianumero": "id",
        "Voimassaolon alkamispvm": "start_dt",
        "Voimassaolon päättymispvm": "end_dt",
        "Hetu": "national_id_number",
        "Osoite": "address_line",
        "Postitoimipaikka": "city",
        "Rekisterinumerot": "registration_number",
    }

    def __init__(self, f):
        self.reader = csv.DictReader(f)
        self._header_row = next(self.reader)
        for header in self.HEADER_FIELD_MAPPING.keys():
            if header not in self._header_row:
                raise ValueError(
                    f'Missing the required column "{header}" in the CSV file.'
                )
        self._fieldnames = [
            self.HEADER_FIELD_MAPPING.get(header, header) for header in self._header_row
        ]
        self.reader.fieldnames = self._fieldnames

    def __iter__(self):
        return self

    def pre_process_row(self, row: dict):
        fields = self.HEADER_FIELD_MAPPING.values()
        return {k: v for k, v in row.items() if k in fields}

    def __next__(self):
        row = self.pre_process_row(next(self.reader))
        permit = PasiResidentPermit(**row)
        return permit


class Command(BaseCommand):
    help = "Import CSV file exported from PASI."
    PermitAddressType = Literal["PRIMARY", "OTHER"]

    def handle(self, *args, **options):
        raise NotImplementedError

    def process_pasi_permit(self, pasi_permit: PasiResidentPermit):
        # Skip all permits that already exists in the database.
        if self.permit_exists(pasi_permit.id):
            raise PasiPermitExists

        # Validation & initialization
        person_info = self.get_person_info(pasi_permit.national_id_number)
        permit_address_type = self.find_permit_address_type(pasi_permit, person_info)
        vehicle = self.fetch_vehicle(pasi_permit.registration_number)
        self.validate_vehicle(pasi_permit, vehicle)

        primary_address = self.update_or_create_address(person_info["primary_address"])
        other_address = self.update_or_create_address(person_info["other_address"])
        customer = self.update_or_create_customer(
            person_info, primary_address, other_address, pasi_permit.language
        )
        raise NotImplementedError(permit_address_type, customer)

    @staticmethod
    def permit_exists(id_):
        return bool(id_) and ParkingPermit.objects.filter(id=id_).exists()

    @staticmethod
    def get_person_info(national_id_number: str) -> dvv.DvvPersonInfo:
        try:
            person_info = dvv.get_person_info(national_id_number)
        except Exception as e:
            raise PasiImportError("Something went wrong during DVV request") from e

        if not person_info:
            raise PasiValidationError("Could not find customer in DVV")

        return person_info

    @staticmethod
    def _address_info_matches_pasi_permit_address(
        pasi_permit: PasiResidentPermit, address_info: dvv.DvvAddressInfo
    ) -> bool:
        if not address_info:
            return False

        def normalize_str(s: str):
            return s.lower().strip()

        street_name = normalize_str(address_info["street_name"])
        street_name_sv = normalize_str(address_info["street_name_sv"])
        street_number = normalize_str(address_info["street_number"])
        pasi_street_name = normalize_str(pasi_permit.street_name)
        pasi_street_number = normalize_str(pasi_permit.street_number)

        name_matches = street_name.startswith(pasi_street_name)
        name_sv_matches = street_name_sv.startswith(pasi_street_name)
        number_matches = street_number.startswith(pasi_street_number)

        return name_matches or name_sv_matches and number_matches

    def find_permit_address_type(
        self, pasi_permit: PasiResidentPermit, person_info: dvv.DvvPersonInfo
    ) -> PermitAddressType:
        if self._address_info_matches_pasi_permit_address(
            pasi_permit, person_info["primary_address"]
        ):
            return "PRIMARY"
        if self._address_info_matches_pasi_permit_address(
            pasi_permit, person_info["other_address"]
        ):
            return "OTHER"

        raise PasiValidationError(
            "Could not find an address matching the PASI permit address."
        )

    @staticmethod
    def get_permit_address_from_customer(
        customer: Customer, permit_address_type: PermitAddressType
    ):
        if permit_address_type == "PRIMARY":
            return customer.primary_address
        if permit_address_type == "OTHER":
            return customer.other_address
        raise ValueError(f'Unknown PermitAddressType "{permit_address_type}"')

    @staticmethod
    def update_or_create_address(address_info: dvv.DvvAddressInfo):
        if not address_info:
            return None

        location = Point(*address_info["location"], srid=settings.SRID)
        address, _created = Address.objects.update_or_create(
            street_name=address_info["street_name"],
            street_number=address_info["street_number"],
            city=address_info["city"].title() if address_info["city"] else "",
            postal_code=address_info["postal_code"],
            location=location,
        )
        return address

    @staticmethod
    def update_or_create_customer(
        person_info: dvv.DvvPersonInfo,
        primary_address: Address,
        other_address: Address,
        language: str,
    ):
        customer_data = {
            "first_name": person_info.get("first_name", ""),
            "last_name": person_info.get("last_name", ""),
            "national_id_number": person_info["national_id_number"],
            "email": person_info["email"],
            "phone_number": person_info["phone_number"],
            "address_security_ban": person_info["address_security_ban"],
            "driver_license_checked": person_info["driver_license_checked"],
            "primary_address": primary_address,
            "other_address": other_address,
            "language": language,
        }

        customer, _created = Customer.objects.update_or_create(
            national_id_number=person_info["national_id_number"], defaults=customer_data
        )

        return customer

    @staticmethod
    def fetch_vehicle(registration_number: str) -> Vehicle:
        try:
            return Traficom().fetch_vehicle_details(registration_number)
        except Exception as e:
            raise PasiImportError(
                "Something went wrong during Traficom vehicle fetch"
            ) from e

    @staticmethod
    def validate_vehicle(pasi_permit: PasiResidentPermit, vehicle: Vehicle) -> NoReturn:
        if not vehicle.users.filter(
            national_id_number=pasi_permit.national_id_number
        ).exists():
            raise PasiValidationError(
                f"Vehicle {vehicle.registration_number} does not belong to customer"
            )
