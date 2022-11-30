import dataclasses

import freezegun
import pytest
from django.utils import timezone

from parking_permits.management.commands.import_pasi_csv import PasiResidentPermit


@pytest.fixture
def pasi_resident_permit():
    with freezegun.freeze_time("2000-01-01 00:00:00"):
        return PasiResidentPermit(
            id=123,
            start_dt=timezone.now(),
            end_dt=timezone.now() + timezone.timedelta(days=30),
            national_id_number="123456-XXXX",
            address_line="Street Name 1",
            registration_number="FOO-123",
        )


class TestPasiResidentPermit:
    def test_header_mapping_field_names_should_exist(self, pasi_resident_permit):
        for v in PasiResidentPermit.CSV_HEADER_TO_FIELD.values():
            if v is None:
                continue
            assert getattr(pasi_resident_permit, v)

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
        pasi_resident_permit = dataclasses.replace(
            pasi_resident_permit, address_line=address_line
        )
        assert pasi_resident_permit.street_name == street_name
        assert pasi_resident_permit.street_number == street_number
