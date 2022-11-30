import typing
from dataclasses import dataclass, field
from datetime import datetime

from django.core.management import BaseCommand

from parking_permits.services import kmo


class Command(BaseCommand):
    help = "Import CSV file exported from Pasi."

    def handle(self, *args, **options):
        pass


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
    start_dt: datetime
    end_dt: datetime
    national_id_number: str
    address_line: str
    registration_number: str

    _street_name: typing.Optional[str] = field(init=False, default=None)
    _street_number: typing.Optional[str] = field(init=False, default=None)

    def __setattr__(self, key, value):
        super(PasiResidentPermit, self).__setattr__(key, value)
        if key == "address_line":
            self._compute_street_name_and_number()

    def _compute_street_name_and_number(self):
        self._street_name, self._street_number = kmo.parse_street_name_and_number(
            self.address_line
        )

    @property
    def street_name(self):
        return self._street_name

    @property
    def street_number(self):
        return self._street_number
