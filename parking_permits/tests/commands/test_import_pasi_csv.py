import os
import zoneinfo
from datetime import datetime

import freezegun
import pytest
from django.utils import timezone

from parking_permits.management.commands.import_pasi_csv import (
    PasiCsvReader,
    PasiResidentPermit,
    parse_pasi_datetime,
)


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


class TestPasiCsvReader:
    def test_header_mapping_field_names_should_exist(self, pasi_resident_permit):
        for v in PasiCsvReader.HEADER_FIELD_MAPPING.values():
            if v is None:
                continue
            assert getattr(pasi_resident_permit, v)

    def test_smoke_test(self, pasi_permits_csv):
        reader = PasiCsvReader(pasi_permits_csv)
        for row in reader:
            print(row)
