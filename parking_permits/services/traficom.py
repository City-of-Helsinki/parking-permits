import logging
import ssl
import xml.etree.ElementTree as ET  # noqa: N817

import requests
from django.conf import settings
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import TraficomFetchVehicleError
from parking_permits.models.driving_class import DrivingClass
from parking_permits.models.vehicle import (
    EmissionType,
    Vehicle,
    VehicleClass,
    VehiclePowerType,
    VehicleUser,
)

ssl.match_hostname = lambda cert, hostname: True

logger = logging.getLogger("db")


VEHICLE_RESTRICTIONS = {
    "03": _("ajokielto"),
    "07": _("valvontakatsastusvelvollisuus laiminlyöty"),
    "10": _("määräaikaiskatsastus suorittamatta/hylätty"),
    "11": _("ajoneuvo anastettu"),
    "18": _("liikenteestä poisto"),
    "19": _("lopullinen poisto"),
    "20": _("rekisteristä poisto"),
    "22": _("ajoneuvovero erääntynyt"),
    "23": _("ajoneuvo käyttökiellossa/lisävero"),
    "24": _("vanha ajoneuvo-/dieselvero erääntynyt"),
    "25": _("kilpien haltuunotto"),
    "34": _("ajokielto kilpien haltuunotosta"),
}

# these codes will raise an error and prevent adding a permit
BLOCKING_VEHICLE_RESTRICTIONS = ("18", "19")

CONSUMPTION_TYPE_NEDC = "4"
CONSUMPTION_TYPE_WLTP = "10"
VEHICLE_TYPE = 1
LIGHT_WEIGHT_VEHICLE_TYPE = 2
VEHICLE_SEARCH = 841
DRIVING_LICENSE_SEARCH = 890

POWER_TYPE_MAPPER = {
    "01": "Bensin",
    "02": "Diesel",
    "03": "Bifuel",
    "04": "Electric",
}

VEHICLE_SUB_CLASS_MAPPER = {
    "900": VehicleClass.L3eA1,
    "905": VehicleClass.L3eA2,
    "906": VehicleClass.L3eA3,
    "907": VehicleClass.L3eA1E,
    "908": VehicleClass.L3eA2E,
    "909": VehicleClass.L3eA3E,
    "910": VehicleClass.L3eA1T,
    "911": VehicleClass.L3eA2T,
    "912": VehicleClass.L3eA3T,
    "916": VehicleClass.L5eA,
    "917": VehicleClass.L5eB,
    "919": VehicleClass.L6eBP,
    "920": VehicleClass.L6eBU,
}


class Traficom:
    url = settings.TRAFICOM_ENDPOINT
    headers = {"Content-type": "application/xml"}

    def fetch_vehicle_details(self, registration_number):
        et = self._fetch_info(registration_number=registration_number)
        vehicle_detail = et.find(".//ajoneuvonTiedot")

        if not vehicle_detail:
            raise TraficomFetchVehicleError(
                _(
                    "Could not find vehicle detail with given %(registration_number)s registration number"
                )
                % {"registration_number": registration_number}
            )

        vehicle_class = vehicle_detail.find("ajoneuvoluokka").text
        vehicle_sub_class = vehicle_detail.findall("ajoneuvoryhmat/ajoneuvoryhma")
        if (
            vehicle_sub_class
            and VEHICLE_SUB_CLASS_MAPPER.get(vehicle_sub_class[-1].text, None)
            is not None
        ):
            vehicle_class = VEHICLE_SUB_CLASS_MAPPER.get(vehicle_sub_class[-1].text)

        if vehicle_class not in VehicleClass:
            raise TraficomFetchVehicleError(
                _(
                    "Unsupported vehicle class %(vehicle_class)s for %(registration_number)s"
                )
                % {
                    "vehicle_class": vehicle_class,
                    "registration_number": registration_number,
                }
            )

        restrictions = []

        for restriction in et.findall(".//rajoitustiedot/rajoitustieto"):
            try:
                restriction_type = restriction.find("rajoitusLaji").text
            except AttributeError:
                continue

            if restriction_type in VEHICLE_RESTRICTIONS:
                message = _("Rajoituslaji %(type): %(description)") % {
                    "type": restriction_type,
                    "description": VEHICLE_RESTRICTIONS[restriction_type],
                }

                if restriction_type in BLOCKING_VEHICLE_RESTRICTIONS:
                    raise TraficomFetchVehicleError(
                        message
                        + " "
                        + _("Ajoneuvon tiedot - Liikenneasioidenrekisteri, Traficom")
                    )

                restrictions.append(message)

        vehicle_identity = et.find(".//tunnus")
        motor = et.find(".//moottori")
        owners_et = et.findall(".//omistajatHaltijat/omistajaHaltija")
        emissions = motor.findall("kayttovoimat/kayttovoima/kulutukset/kulutus")
        inspection_detail = et.find(".//ajoneuvonPerustiedot")
        last_inspection_date = inspection_detail.find("mkAjanLoppupvm")
        emission_type = EmissionType.NEDC
        co2emission = None
        for e in emissions:
            kulutuslaji = e.find("kulutuslaji").text
            if (
                kulutuslaji == CONSUMPTION_TYPE_NEDC
                or kulutuslaji == CONSUMPTION_TYPE_WLTP
            ):
                co2emission = e.find("maara").text
                if kulutuslaji == CONSUMPTION_TYPE_WLTP:
                    emission_type = EmissionType.WLTP

        mass = et.find(".//massa")
        module_weight = mass.find("modulinKokonaismassa")
        technical_weight = mass.find("teknSuurSallKokmassa")
        weight = module_weight if module_weight is not None else technical_weight

        vehicle_power_type = motor.find("kayttovoima")
        vehicle_manufacturer = vehicle_detail.find("merkkiSelvakielinen")
        vehicle_model = vehicle_detail.find("mallimerkinta")
        vehicle_serial_number = vehicle_identity.find("valmistenumero")
        user_ssns = [
            owner_et.find("omistajanTunnus").text
            if owner_et.find("omistajanTunnus") is not None
            else ""
            for owner_et in owners_et
        ]
        power_type = VehiclePowerType.objects.get_or_create(
            identifier=vehicle_power_type.text,
            defaults={"name": POWER_TYPE_MAPPER.get(vehicle_power_type.text, None)},
        )
        vehicle_details = {
            "updated_from_traficom_on": str(tz.now().date()),
            "power_type": power_type[0],
            "vehicle_class": vehicle_class,
            "manufacturer": vehicle_manufacturer.text,
            "model": vehicle_model.text if vehicle_model is not None else "",
            "weight": int(weight.text) if weight else 0,
            "registration_number": registration_number,
            "euro_class": 6,  # It will always be 6 class atm.
            "emission": float(co2emission) if co2emission else 0,
            "emission_type": emission_type,
            "serial_number": vehicle_serial_number.text,
            "last_inspection_date": last_inspection_date.text
            if last_inspection_date is not None
            else None,
        }
        vehicle_users = []
        for user_nin in user_ssns:
            user = VehicleUser.objects.get_or_create(national_id_number=user_nin)
            vehicle_users.append(user[0])
        vehicle = Vehicle.objects.update_or_create(
            registration_number=registration_number, defaults=vehicle_details
        )[0]
        vehicle.users.set(vehicle_users)
        vehicle.restrictions = restrictions
        return vehicle

    def fetch_driving_licence_details(self, hetu):
        et = self._fetch_info(hetu=hetu)
        driving_licence_et = et.find(".//ajokorttiluokkatieto")
        if driving_licence_et.find("ajooikeusluokat") is None:
            raise TraficomFetchVehicleError(
                _(
                    "According to the Digital and Population Data Services Agency, "
                    "you do not live in the Resident parking area. "
                    "If you have just moved to a Resident parking area, "
                    "contact Digital and Population Data Services Agency."
                )
            )

        driving_licence_categories_et = driving_licence_et.findall(
            "viimeisinajooikeus/ajooikeusluokka"
        )
        categories = [
            category.find("ajooikeusluokka").text
            for category in driving_licence_categories_et
        ]

        driving_classes = []
        for category in categories:
            driving_class = DrivingClass.objects.get_or_create(identifier=category)
            driving_classes.append(driving_class[0])

        return {
            "driving_classes": driving_classes,
            "issue_date": driving_licence_et.find("ajokortinMyontamisPvm").text,
        }

    def _fetch_info(self, registration_number=None, hetu=None):
        is_l_type_vehicle = (
            len(registration_number) == 6 if registration_number else False
        )
        vehicle_payload = f"""
            <laji>{LIGHT_WEIGHT_VEHICLE_TYPE if is_l_type_vehicle else VEHICLE_TYPE}</laji>
            <rekisteritunnus>{registration_number}</rekisteritunnus>
        """
        hetu_payload = f"<hetu>{hetu}</hetu>"
        payload = f"""
        <kehys xsi:noNamespaceSchemaLocation="schema.xsd" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
           <yleinen>
              <sanomatyyppi>{settings.TRAFICOM_SANOMA_TYYPPI}</sanomatyyppi>
              <sovellus>{settings.TRAFICOM_SOVELLUS}</sovellus>
              <ymparisto>{settings.TRAFICOM_YMPARISTO}</ymparisto>
              <kayttooikeudet>
                 <tietojarjestelma>
                    <tunnus>{settings.TRAFICOM_USERNAME}</tunnus>
                    <salasana>{settings.TRAFICOM_PASSWORD}</salasana>
                 </tietojarjestelma>
                 <kayttaja />
              </kayttooikeudet>
           </yleinen>
           <sanoma>
              <ajoneuvonHakuehdot>
                 {vehicle_payload if registration_number else hetu_payload}
                 <kyselylaji>{VEHICLE_SEARCH if registration_number else DRIVING_LICENSE_SEARCH}</kyselylaji>
                 <kayttotarkoitus>4</kayttotarkoitus>
                 <asiakas>{settings.TRAFICOM_ASIAKAS}</asiakas>
                 <soku-tunnus>{settings.TRAFICOM_SOKU_TUNNUS}</soku-tunnus>
                 <palvelutunnus>{settings.TRAFICOM_PALVELU_TUNNUS}</palvelutunnus>
              </ajoneuvonHakuehdot>
           </sanoma>
        </kehys>
        """

        response = requests.post(
            self.url,
            data=payload,
            headers=self.headers,
            verify=settings.TRAFICOM_VERIFY_SSL,
        )
        if response.status_code >= 300:
            logger.error(f"Fetching data from traficom failed. Error: {response.text}")
            raise TraficomFetchVehicleError(_("Failed to fetch data from traficom"))

        return ET.fromstring(response.text)
