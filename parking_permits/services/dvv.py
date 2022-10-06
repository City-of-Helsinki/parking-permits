import base64
import json
import logging

import requests
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from parking_permits.exceptions import ObjectNotFound
from parking_permits.models import ParkingZone
from parking_permits.services.kmo import (
    get_address_details,
    parse_street_name_and_number,
)

logger = logging.getLogger("db")


def get_auth_token():
    auth = f"{settings.DVV_USERNAME}:{settings.DVV_PASSWORD}"
    return base64.b64encode(auth.encode("utf-8")).decode("utf-8")


def get_request_headers():
    token = get_auth_token()
    return {"Authorization": f"Basic {token}"}


def get_request_data(hetu):
    return {
        "Henkilotunnus": hetu,
        "SoSoNimi": settings.DVV_SOSONIMI,
        "Loppukayttaja": settings.DVV_LOPPUKAYTTAJA,
    }


def get_addresses(national_id_number):
    primary_address, other_address = None, None
    if national_id_number:
        customer = get_person_info(national_id_number)
        if not customer:
            raise ObjectNotFound(_("Person not found"))
        primary_address = _extract_address_data(customer.get("primary_address"))
        other_address = _extract_address_data(customer.get("other_address"))
    return primary_address, other_address


def _extract_address_data(address):
    return (
        {
            "street_name": address.get("street_name"),
            "street_number": address.get("street_number"),
            "city": address.get("city"),
            "postal_code": address.get("postal_code"),
        }
        if address
        else None
    )


def format_address(address_data):
    # DVV combines the street name, street number and apartment
    # building number together in a single string. We only need
    # to use the street name and street number

    parsed_address = parse_street_name_and_number(address_data["LahiosoiteS"])
    street_name = parsed_address.get("street_name")
    street_number = parsed_address.get("street_number")
    parsed_address_sv = parse_street_name_and_number(address_data["LahiosoiteR"])
    street_name_sv = parsed_address_sv.get("street_name")
    address_detail = get_address_details(street_name, street_number)
    try:
        zone = ParkingZone.objects.get_for_location(address_detail["location"])
    except ParkingZone.DoesNotExist:
        zone = None

    return {
        **address_detail,
        "street_name": street_name,
        "street_name_sv": street_name_sv,
        "street_number": street_number,
        "city_sv": address_data["PostitoimipaikkaR"],
        "city": address_data["PostitoimipaikkaS"],
        "postal_code": address_data["Postinumero"],
        "zone": zone,
    }


def is_valid_address(address):
    return (
        address["LahiosoiteS"] != ""
        and address["PostitoimipaikkaS"]
        and address["PostitoimipaikkaS"].upper() == "HELSINKI"
    )


def get_person_info(national_id_number):
    logger.info(f"Retrieving person info with national_id_number: {national_id_number}")
    data = get_request_data(national_id_number)
    headers = get_request_headers()
    response = requests.post(
        settings.DVV_PERSONAL_INFO_URL,
        json.dumps(data),
        headers=headers,
    )
    if not response.ok:
        logger.error(
            f"Invalid DVV response for {national_id_number}. Response: {response.text}"
        )
        return None

    response_data = response.json()
    # DVV does not return a 404 code if the given hetu
    # is not found, so we need to check the response
    # content
    person_info = response_data.get("Henkilo")
    if not person_info:
        logger.error(f"Person info not found: {national_id_number}")
        return None

    last_name = person_info["NykyinenSukunimi"]["Sukunimi"]
    first_name = person_info["NykyisetEtunimet"]["Etunimet"]
    permanent_address = person_info["VakinainenKotimainenLahiosoite"]
    temporary_address = person_info["TilapainenKotimainenLahiosoite"]
    primary_address = (
        format_address(permanent_address)
        if is_valid_address(permanent_address)
        else None
    )
    other_address = (
        format_address(temporary_address)
        if is_valid_address(temporary_address)
        else None
    )
    return {
        "national_id_number": national_id_number,
        "first_name": first_name,
        "last_name": last_name,
        "primary_address": primary_address,
        "other_address": other_address,
        "phone_number": "",
        "email": "",
        "address_security_ban": False,
        "driver_license_checked": False,
    }
