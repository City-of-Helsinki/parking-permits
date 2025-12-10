import logging

from django.db import transaction

from parking_permits.models import ParkingZone

from .wfs_importer import WfsImporter

logger = logging.getLogger("db")

PARKING_ZONE_DESCRIPTION_SV = {
    "A": "Kampen",
    "B": "Rödbergen/Eira",
    "C": "Gardesstaden/Ulrikasborg/Brunnsparken",
    "D": "Skatudden",
    "DC": "Sveaborg",
    "E": "Gloet/Kronohagen",
    "F": "Främre Tölö",
    "H": "Bortre Tölö/Mejlans",
    "I": "Berghäll/Sörnäs",
    "J": "Åshöjden",
    "K": "Vallgård",
    "L": "Brunakärr",
    "M": "Södra Haga",
    "N": "Drumsö",
    "O": "Munksnäs",
    "P": "Munkshöjden/Näshöjden",
}


class ParkingZoneImporter(WfsImporter):
    """
    Imports parking zones data from kartta.hel.fi.
    """

    wfs_typename = "Asukas_ja_yrityspysakointivyohykkeet_alue"

    def import_parking_zones(self):
        parking_zone_dicts = self.download_and_parse()
        count = self._save_parking_zones(parking_zone_dicts)
        logger.info(f"Created or updated {count} parking zones")

    @transaction.atomic
    def _save_parking_zones(self, parking_zone_dicts):
        logger.info("Saving parking zones.")
        count = 0
        parking_zone_ids = []
        for parking_zone in parking_zone_dicts:
            parking_zone, _ = ParkingZone.objects.update_or_create(
                name=parking_zone["name"], defaults=parking_zone
            )
            parking_zone_ids.append(parking_zone.pk)
            count += 1
        ParkingZone.objects.exclude(pk__in=parking_zone_ids).delete()
        return count

    def _parse_feature(self, feature):
        name = feature["properties"]["asukaspysakointitunnus"]
        description = feature["properties"]["alueen_nimi"]
        description_sv = PARKING_ZONE_DESCRIPTION_SV.get(name, "")
        locations = self.convert_to_geosgeometry(feature["geometry"])

        return {
            "name": name,
            "description": description,
            "description_sv": description_sv,
            "location": locations,
        }
