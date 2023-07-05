import csv
import dataclasses
import re
import traceback
import zoneinfo
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, NoReturn, Optional

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management import BaseCommand
from django.db import transaction
from django.utils import timezone

from parking_permits.models import Address, Customer, Order, ParkingPermit, Vehicle
from parking_permits.models.order import OrderStatus
from parking_permits.models.parking_permit import ContractType, ParkingPermitStatus
from parking_permits.services import dvv, kami
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


class PasiDryRun(PasiImportError):
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
    """Represents a single row in the CSV exported from PASI."""

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
    _apartment: Optional[str] = dataclasses.field(init=False, default=None)

    @address_line.setter
    def address_line(self, val):
        self._address_line = val
        (
            self._street_name,
            self._street_number,
            self._apartment,
        ) = kami.parse_street_data(self.address_line)

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

    @property
    def month_count(self):
        dt_end_start = relativedelta(self.end_dt, self.start_dt)

        month_count = dt_end_start.years * 12 + dt_end_start.months
        if dt_end_start.days > 0:
            # Add a month if there are any remainder days.
            month_count += 1

        return month_count


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

        # Validate that the header row has all the required headers
        # (i.e. the ones listed in HEADER_FIELD_MAPPING).
        for header in self.HEADER_FIELD_MAPPING.keys():
            if header not in self._header_row:
                raise ValueError(
                    f'Missing the required column "{header}" in the CSV file.'
                )

        # DictReader's fieldnames attribute relies on order; however, the order of
        # the columns is *not* guaranteed in the PASI CSV, but the column names are.
        # So we generate the field names by mapping what we can and leave the rest
        # as they are.
        self._fieldnames = [
            self.HEADER_FIELD_MAPPING.get(header, header) for header in self._header_row
        ]
        self.reader.fieldnames = self._fieldnames

    def __iter__(self):
        return self

    def pre_process_row(self, row: dict):
        # Filter out the non-relevant fields (the ones that do not exist
        # in HEADER_FIELD_MAPPING)
        fields = self.HEADER_FIELD_MAPPING.values()
        return {k: v for k, v in row.items() if k in fields}

    def __next__(self):
        row = self.pre_process_row(next(self.reader))
        permit = PasiResidentPermit(**row)
        return permit


class Command(BaseCommand):
    help = "Import CSV file exported from PASI."
    PermitAddressType = Literal["PRIMARY", "OTHER"]

    def add_arguments(self, parser):
        parser.add_argument("source_file", help="Path to the CSV file to import.")
        parser.add_argument(
            "--encoding",
            default="utf-8-sig",
            help="Set the encoding used for reading the CSV file. Defaults to utf-8-sig",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the import without actually creating anything.",
        )

    def handle(self, *args, **options):
        encoding = options["encoding"]
        with open(options["source_file"], mode="r", encoding=encoding) as f:
            filename = f.name.split("/")[-1]
            reader = PasiCsvReader(f)
            for idx, pasi_permit in enumerate(reader, start=2):

                def prefix(msg):
                    return f"{filename}:{idx} ID: {pasi_permit.id:9} {msg}"

                captured_exc = None
                try:
                    with transaction.atomic():
                        created_permit = self.process_pasi_permit(pasi_permit)
                        if options["dry_run"] is True:
                            raise PasiDryRun
                except PasiPermitExists:
                    continue
                except PasiDryRun:
                    self.stdout.write(
                        self.style.SUCCESS(prefix("Success, rolling back"))
                    )
                except PasiValidationError as exc:
                    captured_exc = exc
                    self.stdout.write(
                        self.style.NOTICE(prefix(f"Validation error: {exc}"))
                    )
                except PasiImportError as exc:
                    captured_exc = exc
                    self.stdout.write(
                        self.style.ERROR(prefix(f"Error while importing: {exc}"))
                    )
                    self.stderr.write(traceback.format_exc())
                except Exception as exc:
                    captured_exc = exc
                    self.stdout.write(
                        self.style.ERROR(prefix(f"Unexpected error: {exc}"))
                    )
                    self.stderr.write(traceback.format_exc())
                else:
                    self.stdout.write(
                        self.style.SUCCESS(prefix(f"Created permit {created_permit}"))
                    )
                finally:
                    if captured_exc is not None:
                        self.stderr.write(traceback.format_exc())

        self.stdout.write(self.style.SUCCESS("Finished!"))

    def process_pasi_permit(self, pasi_permit: PasiResidentPermit):
        self.pre_process(pasi_permit)

        # Validation & initialization
        person_info = self.get_person_info(pasi_permit.national_id_number)
        permit_address_type = self.find_permit_address_type(pasi_permit, person_info)
        vehicle = self.fetch_vehicle(pasi_permit.registration_number)
        self.validate_vehicle(pasi_permit, vehicle)

        # Create/get all the instances required for a parking permit.
        primary_address = self.update_or_create_address(person_info["primary_address"])
        other_address = self.update_or_create_address(person_info["other_address"])
        customer = self.update_or_create_customer(
            person_info, primary_address, other_address, pasi_permit.language
        )
        permit_address = self.get_permit_address_from_customer(
            customer, permit_address_type
        )

        permit = self.create_parking_permit(
            pasi_permit, customer, vehicle, permit_address
        )

        Order.objects.create_for_permits([permit], OrderStatus.CONFIRMED)

        return permit

    @staticmethod
    def create_parking_permit(
        pasi_permit: PasiResidentPermit, customer, vehicle, permit_address
    ):
        return ParkingPermit.objects.create(
            id=pasi_permit.id,
            contract_type=ContractType.FIXED_PERIOD,
            customer=customer,
            vehicle=vehicle,
            parking_zone=permit_address.zone,
            status=ParkingPermitStatus.VALID,
            start_time=pasi_permit.start_dt,
            month_count=pasi_permit.month_count,
            end_time=pasi_permit.end_dt,
            description="Imported from PASI",
            address=permit_address,
            primary_vehicle=True,
        )

    def pre_process(self, pasi_permit: PasiResidentPermit):
        """Perform operations before processing a PASI permit, i.e. do all the simple
        filtering here before moving on to more integration/database heavy stuff."""

        if self.permit_exists(pasi_permit.id):
            raise PasiPermitExists(f"Permit with ID #{pasi_permit.id} already exists")

        if self.vehicle_has_active_permit(pasi_permit.registration_number):
            raise PasiValidationError(
                f"Vehicle {pasi_permit.registration_number} already has at least one active permit"
            )

    @staticmethod
    def permit_exists(id_):
        return bool(id_) and ParkingPermit.objects.filter(id=id_).exists()

    @staticmethod
    def vehicle_has_active_permit(registration_number: str) -> bool:
        active_permits_for_vehicle = ParkingPermit.objects.active().filter(
            vehicle__registration_number=registration_number
        )
        return active_permits_for_vehicle.exists()

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
            city=address_info["city"] if address_info["city"] else "",
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
