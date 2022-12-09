import os
import random
import zoneinfo
from datetime import date, datetime
from unittest.mock import patch

import freezegun
import pytest
from django.core.management import call_command
from django.utils import timezone

from parking_permits.management.commands.import_pasi_csv import Command as PasiCommand
from parking_permits.management.commands.import_pasi_csv import (
    PasiCsvReader,
    PasiImportError,
    PasiPermitExists,
    PasiResidentPermit,
    PasiValidationError,
    parse_pasi_datetime,
)
from parking_permits.models import ParkingZone
from parking_permits.models.parking_permit import ParkingPermit, ParkingPermitStatus
from parking_permits.models.vehicle import Vehicle, VehicleUser
from parking_permits.services import dvv
from parking_permits.services.traficom import Traficom
from parking_permits.tests.factories import ParkingZoneFactory
from parking_permits.tests.factories.address import AddressFactory
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.faker import fake
from parking_permits.tests.factories.parking_permit import ParkingPermitFactory
from parking_permits.tests.factories.product import ProductFactory
from parking_permits.tests.factories.vehicle import VehicleFactory


@pytest.fixture(autouse=True)
def no_requests(monkeypatch):
    """Remove requests.sessions.Session.request for all tests."""
    monkeypatch.delattr("requests.sessions.Session.request")


@pytest.fixture
def pasi_resident_permit():
    with freezegun.freeze_time("2000-01-01 00:00:00"):
        return PasiResidentPermit(
            id=123,
            start_dt=timezone.now(),
            end_dt=timezone.now() + timezone.timedelta(days=30),
            national_id_number="123456-XXXX",
            address_line="Street Name 1",
            city="HELSINKI",
            registration_number="FOO-123",
        )


@pytest.fixture
def pasi_permits_csv():
    filepath = os.path.join(os.path.dirname(__file__), "data", "example_permits.csv")
    with open(filepath, "r", encoding="utf-8-sig") as f:
        yield f


class TestPasiResidentPermit:
    @pytest.mark.parametrize(
        "address_line, street_name, street_number",
        [
            ("", "", ""),
            ("Mannerheimintie", "Mannerheimintie", ""),
            ("Mannerheimintie 2", "Mannerheimintie", "2"),
        ],
    )
    def test_pasi_street_address_and_number(
        self, pasi_resident_permit, address_line, street_name, street_number
    ):
        pasi_resident_permit.address_line = address_line
        assert pasi_resident_permit.street_name == street_name
        assert pasi_resident_permit.street_number == street_number

    @pytest.mark.parametrize(
        "timestamp, expected_dt",
        [
            (
                "1.1.1999 1:01",
                datetime(1999, 1, 1, 1, 1, tzinfo=zoneinfo.ZoneInfo("Europe/Helsinki")),
            ),
            (
                "31.12.2021 13:59",
                datetime(
                    2021, 12, 31, 13, 59, tzinfo=zoneinfo.ZoneInfo("Europe/Helsinki")
                ),
            ),
            (
                "13.10.2020 0:00",
                datetime(
                    2020, 10, 13, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Helsinki")
                ),
            ),
        ],
    )
    def test_parse_pasi_datetime(self, timestamp: str, expected_dt: datetime):
        assert parse_pasi_datetime(timestamp) == expected_dt

    def test_language_should_be_sv_if_city_is_helsingfors(self, pasi_resident_permit):
        pasi_resident_permit.city = "Helsingfors"
        assert pasi_resident_permit.language == "sv"

    def test_language_should_be_fi_if_city_is_not_helsingfors(
        self, pasi_resident_permit
    ):
        pasi_resident_permit.city = "Helsinki"
        assert pasi_resident_permit.language == "fi"

    @pytest.mark.parametrize(
        "start_dt, end_dt, expected_count",
        [
            ("1.1.2000 0:00", "31.1.2000 23:59", 1),
            ("1.1.2000 0:00", "1.2.2000 23:59", 1),
            ("1.1.2000 0:00", "2.2.2000 0:00", 2),
            ("1.2.2000 0:00", "2.3.2000 0:00", 2),
            ("1.1.2000 0:00", "2.1.2000 0:00", 1),
            ("1.1.2000 0:00", "31.1.2000 23:59", 1),
            ("1.1.2000 0:00", "1.1.2000 23:59", 0),
            ("1.1.2000 0:00", "31.12.2000 23:59", 12),
            ("1.1.2000 0:00", "31.12.2001 23:59", 24),
        ],
    )
    def test_month_count(self, pasi_resident_permit, start_dt, end_dt, expected_count):
        pasi_resident_permit.start_dt = start_dt
        pasi_resident_permit.end_dt = end_dt

        assert pasi_resident_permit.month_count == expected_count


class TestPasiCsvReader:
    def test_header_mapping_field_names_should_exist(self, pasi_resident_permit):
        for v in PasiCsvReader.HEADER_FIELD_MAPPING.values():
            if v is None:
                continue
            assert getattr(pasi_resident_permit, v)

    @patch.object(
        PasiCsvReader,
        "HEADER_FIELD_MAPPING",
        {"required column that shouldn't exist": "foo"},
    )
    def test_should_validate_required_columns(self, pasi_permits_csv):
        with pytest.raises(ValueError):
            PasiCsvReader(pasi_permits_csv)

    def test_smoke_test(self, pasi_permits_csv):
        reader = PasiCsvReader(pasi_permits_csv)
        for row in reader:
            print(row)


@pytest.mark.django_db
class TestPasiImportCommand:
    def test_permit_exists_return_false_if_none(self):
        assert PasiCommand.permit_exists(None) is False

    def test_permit_exists_return_true_if_permit_exists(self):
        permit = ParkingPermitFactory()

        assert PasiCommand.permit_exists(permit.id) is True

    def test_permit_exists_return_false_if_permit_doesnt_exist(self):
        permit = ParkingPermitFactory()

        assert PasiCommand.permit_exists(permit.id + 1) is False

    @patch("parking_permits.services.dvv.get_person_info", return_value="Hello, world!")
    def test_get_person_info_returns_person_info_from_dvv(self, mock_get_person_info):
        person_info = PasiCommand.get_person_info("112233-123A")

        mock_get_person_info.assert_called_once_with("112233-123A")
        assert person_info == "Hello, world!"

    @patch("parking_permits.services.dvv.get_person_info")
    def test_get_person_info_raises_pasi_error_on_error(self, mock_get_person_info):
        def raise_error(*_, **__):
            raise ValueError

        mock_get_person_info.side_effect = raise_error

        with pytest.raises(PasiImportError):
            PasiCommand.get_person_info("112233-123A")

    @patch("parking_permits.services.dvv.get_person_info", return_value=None)
    def test_get_person_info_raises_pasi_validation_error_on_empty_result(
        self, mock_get_person_info
    ):
        with pytest.raises(PasiValidationError):
            PasiCommand.get_person_info("112233-123A")
        mock_get_person_info.assert_called_once_with("112233-123A")

    @pytest.mark.parametrize(
        "address_line, primary_address, other_address, expected",
        [
            ("Mannerheimintie 1 A 2", None, None, "PRIMARY"),
            ("Jonkuntoisentie 10 B 20", None, None, "OTHER"),
            ("Mannerheimin 1 A 2", None, None, "PRIMARY"),
            ("Mannerheimintie 1", None, None, "PRIMARY"),
            (
                "Mannerheimintie 1 A 2",
                dict(
                    street_name="Mannerheimintie",
                    street_name_sv="Mannerheimvägen",
                    street_number="1 A 2",
                ),
                dict(
                    street_name="Mannerheimintie",
                    street_name_sv="Mannerheimvägen",
                    street_number="1 A 2",
                ),
                "PRIMARY",
            ),
            (
                "Mannerheimvägen 1 A 2",
                dict(street_name_sv="Mannerheimvägen"),
                None,
                "PRIMARY",
            ),
        ],
    )
    def test_find_permit_address_type_returns_correct_type(
        self,
        pasi_resident_permit,
        address_line,
        primary_address,
        other_address,
        expected,
    ):
        primary_address = primary_address or dict()
        primary_address.setdefault("street_name", "Mannerheimintie")
        primary_address.setdefault("street_name_sv", "Samma på svenska")
        primary_address.setdefault("street_number", "1 A 2")

        other_address = other_address or dict()
        other_address.setdefault("street_name", "Jonkuntoisentie")
        other_address.setdefault("street_name_sv", "Samma på svenska")
        other_address.setdefault("street_number", "10 B 20")

        person_info = dict(primary_address=primary_address, other_address=other_address)
        pasi_resident_permit.address_line = address_line
        pasi_command = PasiCommand()

        assert (
            pasi_command.find_permit_address_type(pasi_resident_permit, person_info)
            == expected
        )

    def test_find_permit_address_type_raises_validation_error_if_no_match(
        self, pasi_resident_permit
    ):
        primary_address = dict(
            street_name="Primary Street",
            street_name_sv="Samma på svenska",
            street_number="1",
        )
        other_address = dict(
            street_name="Other Street",
            street_name_sv="Samma på svenska",
            street_number="2",
        )
        person_info = dict(primary_address=primary_address, other_address=other_address)
        pasi_resident_permit.address_line = "Banana Hammock 666"
        pasi_command = PasiCommand()

        with pytest.raises(PasiValidationError):
            pasi_command.find_permit_address_type(pasi_resident_permit, person_info)

    def test_find_permit_address_type_raises_validation_error_if_no_match_null_addresses(
        self, pasi_resident_permit
    ):
        person_info = dict(primary_address=None, other_address=None)
        pasi_command = PasiCommand()

        with pytest.raises(PasiValidationError):
            pasi_command.find_permit_address_type(pasi_resident_permit, person_info)

    def test_get_permit_address_from_customer_returns_primary(self):
        primary_address = AddressFactory()
        customer = CustomerFactory(primary_address=primary_address)

        address = PasiCommand.get_permit_address_from_customer(customer, "PRIMARY")

        assert address is primary_address

    def test_get_permit_address_from_customer_returns_other(self):
        other_address = AddressFactory()
        customer = CustomerFactory(other_address=other_address)

        address = PasiCommand.get_permit_address_from_customer(customer, "OTHER")

        assert address is other_address

    def test_get_permit_address_from_customer_raises_error_on_unknown_type(self):
        customer = CustomerFactory()

        with pytest.raises(ValueError):
            PasiCommand.get_permit_address_from_customer(customer, "BANANA")

    def test_validate_vehicle_passes(self, pasi_resident_permit):
        vehicle = VehicleFactory(registration_number="FOO-123")
        vehicle.users.add(
            VehicleUser.objects.create(
                national_id_number=pasi_resident_permit.national_id_number
            )
        )
        vehicle.users.add(VehicleUser.objects.create(national_id_number="foo"))
        vehicle.users.add(VehicleUser.objects.create(national_id_number="bar"))

        PasiCommand.validate_vehicle(pasi_resident_permit, vehicle)

    def test_validate_vehicle_raises_error_on_failure(self, pasi_resident_permit):
        vehicle = VehicleFactory(registration_number="FOO-123")
        vehicle.users.add(VehicleUser.objects.create(national_id_number="foo"))

        with pytest.raises(PasiValidationError):
            PasiCommand.validate_vehicle(pasi_resident_permit, vehicle)

    @patch.object(Traficom, "fetch_vehicle_details", return_value="Hello, world!")
    def test_fetch_vehicle_gets_vehicle_from_traficom(self, mock_fetch_vehicle_details):
        vehicle = PasiCommand.fetch_vehicle("FOO-123")

        mock_fetch_vehicle_details.assert_called_once_with("FOO-123")
        assert vehicle == "Hello, world!"

    @patch.object(Traficom, "fetch_vehicle_details", return_value="Hello, world!")
    def test_fetch_vehicle_raises_pasi_error_on_failure(
        self, mock_fetch_vehicle_details
    ):
        def raise_error(*_, **__):
            raise ValueError

        mock_fetch_vehicle_details.side_effect = raise_error

        with pytest.raises(PasiImportError):
            PasiCommand.fetch_vehicle("FOO-123")

    def test_vehicle_has_active_permits_returns_true_if_has_active_permits(self):
        vehicle = VehicleFactory(registration_number="FOO-123")
        ParkingPermitFactory(status=ParkingPermitStatus.VALID, vehicle=vehicle)

        assert (
            PasiCommand.vehicle_has_active_permit(vehicle.registration_number) is True
        )

    def test_vehicle_has_active_permits_returns_false_if_no_active_permits(self):
        vehicle = VehicleFactory(registration_number="FOO-123")

        assert (
            PasiCommand.vehicle_has_active_permit(vehicle.registration_number) is False
        )

        ParkingPermitFactory(status=ParkingPermitStatus.CLOSED, vehicle=vehicle)

        assert (
            PasiCommand.vehicle_has_active_permit(vehicle.registration_number) is False
        )

    @patch.object(PasiCommand, "permit_exists", lambda *_, **__: True)
    @patch.object(PasiCommand, "vehicle_has_active_permit", lambda *_, **__: False)
    def test_pre_process_raise_error_if_permit_exists(self, pasi_resident_permit):
        pasi_command = PasiCommand()
        with pytest.raises(PasiPermitExists, match="already exists"):
            pasi_command.pre_process(pasi_resident_permit)

    @patch.object(PasiCommand, "permit_exists", lambda *_, **__: False)
    @patch.object(PasiCommand, "vehicle_has_active_permit", lambda *_, **__: True)
    def test_pre_process_raise_error_if_active_permits(self, pasi_resident_permit):
        pasi_command = PasiCommand()
        with pytest.raises(PasiValidationError, match="has at least one active permit"):
            pasi_command.pre_process(pasi_resident_permit)


@pytest.mark.skip(reason="For local testing. Not a reliable test and not a unit test.")
@pytest.mark.django_db
def test_pasi_command_smoke_test(pasi_permits_csv):
    # Create parking zones
    zone_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for letter in zone_letters:
        zone = ParkingZoneFactory(name=letter)
        ProductFactory(
            zone=zone, start_date=date(1990, 1, 1), end_date=date(2100, 1, 1)
        )
    parking_zones = ParkingZone.objects.all()

    def generate_dvv_address_info() -> dvv.DvvAddressInfo:
        street_name = fake.street_name()
        street_name_sv = f"{street_name} but in Swedish"
        zone = random.choice(parking_zones)
        return dict(
            street_name=street_name,
            street_name_sv=street_name_sv,
            street_number=fake.building_number(),
            city="Helsinki",
            city_sv="Helsingfors",
            postal_code=fake.postcode(),
            zone=zone,
            location=zone.location[0][0][0:3],
        )

    def get_person_info(national_id_number) -> dvv.DvvPersonInfo:
        return dict(
            national_id_number=national_id_number,
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            primary_address=generate_dvv_address_info(),
            other_address=generate_dvv_address_info(),
            phone_number="",
            email="",
            address_security_ban=False,
            driver_license_checked=False,
        )

    def fetch_vehicle_details(_, registration_number):
        try:
            vehicle = Vehicle.objects.get(registration_number=registration_number)
        except Vehicle.DoesNotExist:
            vehicle = VehicleFactory(registration_number=registration_number)
        return vehicle

    args = [os.path.join(os.path.dirname(__file__), "data", "example_permits.csv")]
    opts = {"dry_run": False}
    with (
        patch("parking_permits.services.dvv.get_person_info", get_person_info),
        patch.object(
            PasiCommand, "find_permit_address_type", lambda *_, **__: "PRIMARY"
        ),
        patch.object(Traficom, "fetch_vehicle_details", fetch_vehicle_details),
        patch.object(PasiCommand, "validate_vehicle", lambda *_, **__: True),
    ):
        call_command("import_pasi_csv", *args, **opts)

    reader = PasiCsvReader(pasi_permits_csv)
    for pasi_permit in reader:
        assert ParkingPermit.objects.filter(id=pasi_permit.id).exists()
        parking_permit = ParkingPermit.objects.get(id=pasi_permit.id)
        assert (
            parking_permit.customer.national_id_number == pasi_permit.national_id_number
        )
        assert parking_permit.customer.language == pasi_permit.language
        assert (
            parking_permit.vehicle.registration_number
            == pasi_permit.registration_number
        )
