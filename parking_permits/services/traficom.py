import logging
import ssl
import xml.etree.ElementTree as ET  # noqa: N817

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import TraficomFetchVehicleError
from parking_permits.models.driving_class import DrivingClass
from parking_permits.models.driving_licence import DrivingLicence
from parking_permits.models.parking_permit import ParkingPermit
from parking_permits.models.vehicle import (
    EmissionType,
    LowEmissionCriteria,
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
VEHICLE_SEARCH_NEW = 811
VEHICLE_SEARCH_LEGACY = 841
VEHICLE_SEARCH = (
    VEHICLE_SEARCH_LEGACY
    if settings.TRAFICOM_USE_LEGACY_VEHICLE_FETCH
    else VEHICLE_SEARCH_NEW
)
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


class TraficomVehicleDetailsSynchronizer:
    vehicle_basic_info_path = ".//ajoneuvonPerustiedot"
    motor_path = ".//moottori"

    def __init__(self, registration_number: str):
        self.registration_number = registration_number

    def _serialize(self, response):
        registration_number = self.registration_number
        et = response

        vehicle_info = et.find(".//ajoneuvonTiedot")
        if not vehicle_info:
            raise TraficomFetchVehicleError(
                _(
                    "Could not find vehicle detail with given "
                    "%(registration_number)s registration number"
                )
                % {"registration_number": registration_number}
            )

        vehicle_class = vehicle_info.find("ajoneuvoluokka").text
        vehicle_sub_class = vehicle_info.findall("ajoneuvoryhmat/ajoneuvoryhma")
        if (
            vehicle_sub_class
            and VEHICLE_SUB_CLASS_MAPPER.get(vehicle_sub_class[-1].text, None)
            is not None
        ):
            vehicle_class = VEHICLE_SUB_CLASS_MAPPER.get(vehicle_sub_class[-1].text)

        vehicle_basic_info = et.find(self.vehicle_basic_info_path)
        power = self._get_power(et)

        vehicle_class = self._resolve_vehicle_class(vehicle_class, power)
        if vehicle_class not in VehicleClass:
            raise TraficomFetchVehicleError(
                _(
                    "Unsupported vehicle class %(vehicle_class)s "
                    "for %(registration_number)s"
                )
                % {
                    "vehicle_class": vehicle_class,
                    "registration_number": registration_number,
                }
            )

        restrictions_et = et.findall(".//rajoitustiedot/rajoitustieto")
        restrictions = self._get_restrictions(restrictions_et)

        vehicle_identity = et.find(".//tunnus")
        registration_number_et = et.find(".//rekisteritunnus")
        new_registration_number = self._get_new_registration_number(
            registration_number_et
        )

        owners_et = et.findall(".//omistajatHaltijat/omistajaHaltija")
        last_inspection_date = vehicle_basic_info.find("mkAjanLoppupvm")

        emissions, emission_type, co2emission = self._get_emission_data(et)

        euro_class = EURO_CLASS
        if not co2emission:
            euro_class = EURO_CLASS_WITHOUT_EMISSIONS

        weight = self._get_weight(et)

        vehicle_power_type = self._get_vehicle_power_type(et)
        vehicle_manufacturer = vehicle_info.find("merkkiSelvakielinen")
        vehicle_model = vehicle_info.find("mallimerkinta")
        vehicle_serial_number = vehicle_identity.find("valmistenumero")

        user_ssns = self._get_user_ssns(owners_et)

        return {
            "registration_number": new_registration_number,
            "emissions": emissions,
            "vehicle_power_type": vehicle_power_type,
            "vehicle_class": vehicle_class,
            "vehicle_manufacturer": vehicle_manufacturer,
            "vehicle_model": vehicle_model,
            "euro_class": euro_class,
            "co2emission": co2emission,
            "emission_type": emission_type,
            "weight": weight,
            "vehicle_serial_number": vehicle_serial_number,
            "last_inspection_date": last_inspection_date,
            "restrictions": restrictions,
            "user_ssns": user_ssns,
        }

    @transaction.atomic
    def _sync_with_db(self, vehicle_data) -> Vehicle:
        registration_number = vehicle_data["registration_number"]
        vehicle_power_type = vehicle_data["vehicle_power_type"]
        vehicle_class = vehicle_data["vehicle_class"]
        vehicle_manufacturer = vehicle_data["vehicle_manufacturer"]
        vehicle_model = vehicle_data["vehicle_model"]
        euro_class = vehicle_data["euro_class"]
        co2emission = vehicle_data["co2emission"]
        emission_type = vehicle_data["emission_type"]
        weight = vehicle_data["weight"]
        vehicle_serial_number = vehicle_data["vehicle_serial_number"]
        last_inspection_date = vehicle_data["last_inspection_date"]
        restrictions = vehicle_data["restrictions"]
        user_ssns = vehicle_data["user_ssns"]

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
            "euro_class": euro_class,
            "emission": float(co2emission) if co2emission else 0,
            "emission_type": emission_type,
            "serial_number": vehicle_serial_number.text,
            "last_inspection_date": (
                last_inspection_date.text if last_inspection_date is not None else None
            ),
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

    def _get_power(self, et):
        vehicle_basic_info = et.find(self.vehicle_basic_info_path)
        power = vehicle_basic_info.find(".//suurinNettoteho")
        return power

    def _get_emissions_list(self, et):
        vehicle_basic_info = et.find(self.vehicle_basic_info_path)
        emissions = vehicle_basic_info.findall(
            "tekninen-tieto/kayttovoimat/kayttovoima/kulutukset/kulutus"
        )
        return emissions

    def _get_vehicle_power_type(self, et):
        vehicle_basic_info = et.find(self.vehicle_basic_info_path)
        vehicle_power_type = vehicle_basic_info.find("tekninen-tieto/kayttovoima")
        return vehicle_power_type

    def _get_emission_data(self, et):
        emissions = self._get_emissions_list(et)
        try:
            now = tz.now()
            le_criteria = LowEmissionCriteria.objects.get(
                start_date__lte=now,
                end_date__gte=now,
            )
        except LowEmissionCriteria.DoesNotExist:
            le_criteria = None
            logger.warning(
                "Low emission criteria not found. "
                "Please update LowEmissionCriteria to contain active criteria"
            )

        emission_type = EmissionType.NEDC
        co2emission = None
        for e in emissions:
            kulutuslaji = e.find("kulutuslaji").text
            if kulutuslaji not in CONSUMPTION_TYPE_NEDC + CONSUMPTION_TYPE_WLTP:
                continue
            co2emission = e.find("maara").text

            # if emission are under or equal of the max value of
            # one of the consumption types (WLTP|NEDC) the
            # emission type and value that makes the vehicle eligible
            # for low emissions pricing should be saved to db.
            if kulutuslaji in CONSUMPTION_TYPE_WLTP:
                emission_type = EmissionType.WLTP
                if (
                    le_criteria
                    and float(co2emission) <= le_criteria.wltp_max_emission_limit
                ):
                    break

            elif kulutuslaji in CONSUMPTION_TYPE_NEDC:
                emission_type = EmissionType.NEDC
                if (
                    le_criteria
                    and float(co2emission) <= le_criteria.nedc_max_emission_limit
                ):
                    break

        return emissions, emission_type, co2emission

    def _get_user_ssns(self, owners_et):
        user_ssns = [
            (
                owner_et.find("omistajanTunnus").text
                if owner_et.find("omistajanTunnus") is not None
                else ""
            )
            for owner_et in owners_et
        ]

        if not any(user_ssns):
            raise TraficomFetchVehicleError(
                _("This person has a non-disclosure statement")
            )
        return user_ssns

    def _get_restrictions(self, restrictions_et):
        restrictions = []
        for restriction in restrictions_et:
            try:
                restriction_type = restriction.find("rajoitusLaji").text
            except AttributeError:
                continue

            if restriction_type in BLOCKING_VEHICLE_RESTRICTIONS:
                raise TraficomFetchVehicleError(
                    _("Vehicle %(registration_number)s is decommissioned")
                    % {
                        "registration_number": self.registration_number,
                    }
                )

            if restriction_type in VEHICLE_RESTRICTIONS:
                restrictions.append(restriction_type)
        return restrictions

    def _get_weight_et(self, et):
        vehicle_basic_info = et.find(self.vehicle_basic_info_path)
        weight_et = vehicle_basic_info.find(".//tekninen-tieto/tieliikSuurSallKokmassa")
        return weight_et

    def _get_weight(self, et):
        weight_et = self._get_weight_et(et)
        try:
            weight = safe_cast(weight_et.text, int, 0)
        except AttributeError:
            weight = 0
        if weight and weight >= VEHICLE_MAX_WEIGHT_KG:
            raise TraficomFetchVehicleError(
                _(
                    "Vehicle's %(registration_number)s weight exceeds "
                    "maximum allowed limit"
                )
                % {"registration_number": self.registration_number}
            )
        return weight

    def _get_new_registration_number(self, registration_number_et):
        # "new" as in inferred from the response data instead of referring to the
        # registration number used in the API-call.
        if registration_number_et is not None and registration_number_et.text:
            try:
                new_registration_number = registration_number_et.text.encode(
                    "latin-1"
                ).decode("utf-8")
            except UnicodeDecodeError:
                new_registration_number = registration_number_et.text
        return new_registration_number

    def synchronize(self, *, response) -> Vehicle:
        vehicle_data = self._serialize(response)
        vehicle = self._sync_with_db(vehicle_data)
        return vehicle


class TraficomVehicleDetailsLegacySynchronizer(TraficomVehicleDetailsSynchronizer):
    def _get_power(self, et):
        motor = et.find(self.motor_path)
        power = motor.find(".//suurinNettoteho")
        return power

    def _get_emissions_list(self, et):
        motor = et.find(self.motor_path)
        emissions = motor.findall("kayttovoimat/kayttovoima/kulutukset/kulutus")
        return emissions

    def _get_vehicle_power_type(self, et):
        motor = et.find(self.motor_path)
        vehicle_power_type = motor.find("kayttovoima")
        return vehicle_power_type

    def _get_weight_et(self, et):
        mass = et.find(".//massa")
        weight_et = mass.find("omamassa")
        return weight_et


class Traficom:
    url = settings.TRAFICOM_ENDPOINT
    headers = {"Content-type": "application/xml"}

    def fetch_vehicle_details(
        self, registration_number: str, permit: ParkingPermit | None = None
    ) -> Vehicle:
        if settings.TRAFICOM_USE_LEGACY_VEHICLE_FETCH:
            synchronizer_class = TraficomVehicleDetailsLegacySynchronizer
        else:
            synchronizer_class = TraficomVehicleDetailsSynchronizer

        if self._bypass_traficom(permit):
            return self._fetch_vehicle_from_db(registration_number)

        registration_number = (
            registration_number.strip().upper() if registration_number else ""
        )

        # Fetch vehicle details from Traficom using normal vehicle type
        et = self._fetch_info(
            registration_number=registration_number, is_l_type_vehicle=False
        )
        vehicle_info = et.find(".//ajoneuvonTiedot")

        if not vehicle_info:
            # If normal vehicle was not found, fetch vehicle details
            # from Traficom using light weight vehicle type
            et = self._fetch_info(
                registration_number=registration_number, is_l_type_vehicle=True
            )

        synchronizer = synchronizer_class(registration_number)
        vehicle = synchronizer.synchronize(response=et)
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
                    "Could not find vehicle detail with given "
                    "%(registration_number)s registration number"
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

    def _build_payload(self, *, query_type, query_payload):
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
                 {query_payload}
                 <kyselylaji>{query_type}</kyselylaji>
                 <kayttotarkoitus>4</kayttotarkoitus>
                 <asiakas>{settings.TRAFICOM_ASIAKAS}</asiakas>
                 <soku-tunnus>{settings.TRAFICOM_SOKU_TUNNUS}</soku-tunnus>
                 <palvelutunnus>{settings.TRAFICOM_PALVELU_TUNNUS}</palvelutunnus>
              </ajoneuvonHakuehdot>
           </sanoma>
        </kehys>
        """
        return payload

    def _fetch_info_by_ssn(self, hetu):
        query_payload = f"<hetu>{hetu}</hetu>"
        payload = self._build_payload(
            query_type=DRIVING_LICENSE_SEARCH,
            query_payload=query_payload,
        )

        response = requests.post(
            self.url,
            data=payload,
            headers=self.headers,
            verify=settings.TRAFICOM_VERIFY_SSL,
        )
        return response

    def _fetch_info_by_registration_number(
        self, registration_number, is_l_type_vehicle
    ):
        query_payload = f"""
            <laji>{
            LIGHT_WEIGHT_VEHICLE_TYPE if is_l_type_vehicle else VEHICLE_TYPE
        }</laji>
            <rekisteritunnus>{registration_number}</rekisteritunnus>
        """
        payload = self._build_payload(
            query_type=VEHICLE_SEARCH,
            query_payload=query_payload,
        )

        response = requests.post(
            self.url,
            data=payload,
            headers=self.headers,
            verify=settings.TRAFICOM_VERIFY_SSL,
        )
        return response

    def _fetch_info(self, registration_number=None, hetu=None, is_l_type_vehicle=False):
        if registration_number:
            response = self._fetch_info_by_registration_number(
                registration_number, is_l_type_vehicle
            )
        else:
            response = self._fetch_info_by_ssn(hetu)

        if response.status_code >= 300:
            logger.error(f"Fetching data from traficom failed. Error: {response.text}")
            raise TraficomFetchVehicleError(_("Failed to fetch data from traficom"))

        return ET.fromstring(response.text)
