import logging
import ssl
import xml.etree.ElementTree as ET  # noqa: N817

import requests
from django.conf import settings
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import TraficomFetchVehicleError
from parking_permits.models.driving_class import DrivingClass
from parking_permits.models.driving_licence import DrivingLicence
from parking_permits.models.vehicle import (
    EmissionType,
    Vehicle,
    VehicleClass,
    VehiclePowerType,
    VehicleUser,
)
from parking_permits.utils import safe_cast

ssl.match_hostname = lambda cert, hostname: True

logger = logging.getLogger("db")


VEHICLE_RESTRICTIONS = (
    "03",
    "07",
    "10",
    "11",
    "18",
    "20",
    "22",
    "23",
    "24",
    "25",
    "34",
)

# these codes will raise an error and prevent adding a permit
BLOCKING_VEHICLE_RESTRICTIONS = ("18", "19")

CONSUMPTION_TYPE_NEDC = ("4", "7")
CONSUMPTION_TYPE_WLTP = ("9", "10")
VEHICLE_TYPE = 1
LIGHT_WEIGHT_VEHICLE_TYPE = 2
VEHICLE_SEARCH = 841
DRIVING_LICENSE_SEARCH = 890
NO_DRIVING_LICENSE_ERROR_CODE = "562"
NO_VALID_DRIVING_LICENSE_ERROR_CODE = "578"
VEHICLE_MAX_WEIGHT_KG = 4000
EURO_CLASS = 6  # Default value for vehicles with emission data
EURO_CLASS_WITHOUT_EMISSIONS = 5  # Default value for vehicles without emission data

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
    "907": VehicleClass.L3eA1,
    "908": VehicleClass.L3eA2,
    "909": VehicleClass.L3eA3,
    "910": VehicleClass.L3eA1,
    "911": VehicleClass.L3eA2,
    "912": VehicleClass.L3eA3,
    "916": VehicleClass.L5eA,
    "917": VehicleClass.L5eB,
    "919": VehicleClass.L6eBP,
    "920": VehicleClass.L6eBU,
}


class Traficom:
    url = settings.TRAFICOM_ENDPOINT
    headers = {"Content-type": "application/xml"}

    def _resolve_vehicle_class(self, vehicle_class, power):
        if not vehicle_class.startswith("L3") or vehicle_class in VehicleClass:
            # Not L3 -classed motorcycle or already has accurate classification
            return vehicle_class

        if power is not None and power.text is not None:
            # Classify using power
            power = power.text
            if float(power) <= 11:
                return VehicleClass.L3eA1
            if float(power) <= 35:
                return VehicleClass.L3eA2
            return VehicleClass.L3eA3

        # Fallback to L3eA1 in case traficom doesn't return anything useful
        return VehicleClass.L3eA1

    def fetch_vehicle_details(self, registration_number, permit=None):
        if self._bypass_traficom(permit):
            return self._fetch_vehicle_from_db(registration_number)

        # Fetch vehicle details from Traficom using normal vehicle type
        et = self._fetch_info(
            registration_number=registration_number, is_l_type_vehicle=False
        )
        vehicle_detail = et.find(".//ajoneuvonTiedot")

        if not vehicle_detail:
            # If normal vehicle was not found, fetch vehicle details from Traficom using light weight vehicle type
            et = self._fetch_info(
                registration_number=registration_number, is_l_type_vehicle=True
            )
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

        motor = et.find(".//moottori")
        power = motor.find(".//suurinNettoteho")

        vehicle_class = self._resolve_vehicle_class(vehicle_class, power)

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

            if restriction_type in BLOCKING_VEHICLE_RESTRICTIONS:
                raise TraficomFetchVehicleError(
                    _("Vehicle %(registration_number)s is decommissioned")
                    % {
                        "registration_number": registration_number,
                    }
                )

            if restriction_type in VEHICLE_RESTRICTIONS:
                restrictions.append(restriction_type)

        vehicle_identity = et.find(".//tunnus")
        registration_number_et = et.find(".//rekisteritunnus")
        if registration_number_et is not None and registration_number_et.text:
            registration_number = registration_number_et.text

        owners_et = et.findall(".//omistajatHaltijat/omistajaHaltija")
        emissions = motor.findall("kayttovoimat/kayttovoima/kulutukset/kulutus")
        inspection_detail = et.find(".//ajoneuvonPerustiedot")
        last_inspection_date = inspection_detail.find("mkAjanLoppupvm")
        emission_type = EmissionType.NEDC
        co2emission = None
        for e in emissions:
            kulutuslaji = e.find("kulutuslaji").text
            if kulutuslaji in CONSUMPTION_TYPE_NEDC + CONSUMPTION_TYPE_WLTP:
                co2emission = e.find("maara").text
                if kulutuslaji in CONSUMPTION_TYPE_WLTP:
                    emission_type = EmissionType.WLTP
        euro_class = EURO_CLASS
        if not co2emission:
            euro_class = EURO_CLASS_WITHOUT_EMISSIONS

        mass = et.find(".//massa")
        weight_et = mass.find("omamassa")
        try:
            weight = safe_cast(weight_et.text, int, 0)
        except AttributeError:
            weight = 0
        if weight and weight >= VEHICLE_MAX_WEIGHT_KG:
            raise TraficomFetchVehicleError(
                _(
                    "Vehicle's %(registration_number)s weight exceeds maximum allowed limit"
                )
                % {"registration_number": registration_number}
            )

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
            "registration_number": registration_number,
            "updated_from_traficom_on": str(tz.now().date()),
            "power_type": power_type[0],
            "vehicle_class": vehicle_class,
            "manufacturer": vehicle_manufacturer.text,
            "model": vehicle_model.text if vehicle_model is not None else "",
            "weight": weight,
            "registration_number": registration_number,
            "euro_class": euro_class,
            "emission": float(co2emission) if co2emission else 0,
            "emission_type": emission_type,
            "serial_number": vehicle_serial_number.text,
            "last_inspection_date": last_inspection_date.text
            if last_inspection_date is not None
            else None,
            "restrictions": restrictions or [],
        }
        vehicle_users = []
        for user_nin in user_ssns:
            user = VehicleUser.objects.get_or_create(national_id_number=user_nin)
            vehicle_users.append(user[0])
        vehicle = Vehicle.objects.update_or_create(
            registration_number=registration_number, defaults=vehicle_details
        )[0]
        vehicle.users.set(vehicle_users)
        return vehicle

    def fetch_driving_licence_details(self, hetu, permit=None):
        if self._bypass_traficom(permit):
            return self._fetch_driving_licence_details_from_db(hetu)

        error_code = None
        et = self._fetch_info(hetu=hetu)
        driving_licence_et = et.find(".//ajokorttiluokkatieto")
        try:
            error_code = et.find(".//yleinen/virhe/virhekoodi").text
        except AttributeError:
            pass
        if error_code == NO_DRIVING_LICENSE_ERROR_CODE:
            raise TraficomFetchVehicleError(_("The person has no driving licence"))
        if (
            error_code == NO_VALID_DRIVING_LICENSE_ERROR_CODE
            or driving_licence_et.find("ajooikeusluokat") is None
        ):
            raise TraficomFetchVehicleError(_("No valid driving licence"))

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

    def _fetch_vehicle_from_db(self, registration_number):
        try:
            return Vehicle.objects.get(registration_number=registration_number)
        except Vehicle.DoesNotExist:
            raise TraficomFetchVehicleError(
                _(
                    "Could not find vehicle detail with given %(registration_number)s registration number"
                )
                % {"registration_number": registration_number}
            )

    def _fetch_driving_licence_details_from_db(self, hetu):
        licence = DrivingLicence.objects.filter(
            customer__national_id_number=hetu
        ).first()
        if licence is None:
            raise TraficomFetchVehicleError(_("The person has no driving licence"))
        return {
            "issue_date": licence.start_date,
            "driving_classes": licence.driving_classes.all(),
        }

    def _bypass_traficom(self, permit=None):
        if settings.TRAFICOM_MOCK:
            return True
        if permit and permit.bypass_traficom_validation:
            return True
        return False

    def _fetch_info(self, registration_number=None, hetu=None, is_l_type_vehicle=False):
        registration_number = (
            registration_number.strip().upper() if registration_number else ""
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
