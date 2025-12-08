import base64
import json
import logging
from typing import Any, Optional, TypedDict

import requests
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import ObjectNotFoundError
from parking_permits.models import Customer, ParkingZone
from parking_permits.services.kami import get_address_details, parse_street_data
from parking_permits.utils import is_valid_city

logger = logging.getLogger("db")


class DvvAddressInfo(TypedDict, total=False):
    street_name: str
    street_name_sv: str
    street_number: str
    apartment: str
    apartment_sv: str
    city: str
    city_sv: str
    postal_code: str
    zone: Optional[ParkingZone]
    location: Optional[Any]


class DvvPersonInfo(TypedDict, total=False):
    national_id_number: str
    first_name: str
    last_name: str
    primary_address: Optional[DvvAddressInfo]
    primary_address_apartment: str
    other_address: Optional[DvvAddressInfo]
    other_address_apartment: str
    phone_number: str
    email: str
    address_security_ban: bool
    driver_license_checked: bool


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
            raise ObjectNotFoundError(_("Person not found"))
        primary_address = _extract_address_data(customer.get("primary_address"))
        other_address = _extract_address_data(customer.get("other_address"))
    return primary_address, other_address


def is_same_address(address, other_address):
    if not address and not other_address:
        return True
    if not address or not other_address:
        return False
    return all(
        address[key] == other_address[key]
        for key in ["street_name", "street_number", "apartment", "city", "postal_code"]
    )


def _extract_address_data(address) -> Optional[DvvAddressInfo]:
    return (
        {
            "street_name": address.get("street_name"),
            "street_name_sv": address.get("street_name_sv"),
            "street_number": address.get("street_number"),
            "apartment": address.get("apartment"),
            "apartment_sv": address.get("apartment_sv"),
            "city": address.get("city"),
            "city_sv": address.get("city_sv"),
            "postal_code": address.get("postal_code"),
            "location": address.get("location"),
        }
        if address
        else None
    )


def format_address(address_data) -> DvvAddressInfo:
    # DVV combines the street name, street number and apartment
    # building number together in a single string. We only need
    # to use the street name and street number

    street_name, street_number, apartment = parse_street_data(
        address_data["LahiosoiteS"]
    )

    if swedish_address := address_data.get("LahiosoiteR"):
        street_name_sv, __, apartment_sv = parse_street_data(swedish_address)
    else:
        street_name_sv, apartment_sv = "", ""

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
        "apartment": apartment,
        "apartment_sv": apartment_sv,
        "city": address_data["PostitoimipaikkaS"],
        "city_sv": address_data["PostitoimipaikkaR"],
        "postal_code": address_data["Postinumero"],
        "zone": zone,
    }


def is_valid_address(address):
    address_valid = address and address["LahiosoiteS"] and address["PostitoimipaikkaS"]
    return address_valid and is_valid_city(address["PostitoimipaikkaS"])


def get_person_info(national_id_number) -> Optional[DvvPersonInfo]:
    logger.info(f"Retrieving person info with national_id_number: {national_id_number}")
    data = get_request_data(national_id_number)
    headers = get_request_headers()
    response = requests.post(
        settings.DVV_PERSONAL_INFO_URL,
        json.dumps(data, default=str),
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

    primary_address, primary_apartment = None, ""
    permanent_address = person_info["VakinainenKotimainenLahiosoite"]

    if is_valid_address(permanent_address):
        primary_address = format_address(permanent_address)
        primary_apartment = primary_address.get("apartment", "")

    other_address, other_apartment = None, ""
    temporary_address = person_info["TilapainenKotimainenLahiosoite"]

    if is_valid_address(temporary_address):
        other_address = format_address(temporary_address)
        other_apartment = other_address.get("apartment", "")

    customer = Customer.objects.filter(national_id_number=national_id_number).first()

    active_permits = customer.active_permits if customer else []

    return {
        "national_id_number": national_id_number,
        "first_name": first_name,
        "last_name": last_name,
        "primary_address": primary_address,
        "other_address": other_address,
        "primary_address_apartment": primary_apartment,
        "other_address_apartment": other_apartment,
        "phone_number": "",
        "email": "",
        "address_security_ban": False,
        "driver_license_checked": False,
        "active_permits": active_permits,
    }
