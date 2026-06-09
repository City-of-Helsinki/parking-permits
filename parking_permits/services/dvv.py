import base64
import json
import logging
from typing import Any, TypedDict

import requests
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import ObjectNotFoundError
from parking_permits.models import Customer, ParkingZone
from parking_permits.services.kami import get_address_details
from parking_permits.utils import is_valid_city

logger = logging.getLogger("db")


DATA_GROUP_PERSON_NAME = "HENKILON_NIMI"
DATA_GROUP_PERMANENT_ADDRESS = "VAKINAINEN_KOTIMAINEN_OSOITE"
DATA_GROUP_TEMPORARY_ADDRESS = "TILAPAINEN_KOTIMAINEN_OSOITE"
DATA_GROUP_ADDRESS_SECURITY_BAN = "TURVAKIELTO"
DEFAULT_REQUEST_DATA_GROUPS = [
    DATA_GROUP_PERSON_NAME,
    DATA_GROUP_PERMANENT_ADDRESS,
    DATA_GROUP_TEMPORARY_ADDRESS,
    DATA_GROUP_ADDRESS_SECURITY_BAN,
]


class DvvAddressInfo(TypedDict, total=False):
    street_name: str
    street_name_sv: str
    street_number: str
    apartment: str
    apartment_sv: str
    city: str
    city_sv: str
    postal_code: str
    zone: ParkingZone | None
    location: Any | None


class DvvPersonInfo(TypedDict, total=False):
    national_id_number: str
    first_name: str
    last_name: str
    primary_address: DvvAddressInfo | None
    primary_address_apartment: str
    other_address: DvvAddressInfo | None
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
    return {
        "accept": "application/json",
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def get_request_data(national_id_numbers, data_groups=None):
    if not isinstance(national_id_numbers, list):
        national_id_numbers = [national_id_numbers]
    if data_groups is None:
        data_groups = DEFAULT_REQUEST_DATA_GROUPS
    return {
        "hetulista": national_id_numbers,
        "tietoryhmat": data_groups,
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


def _extract_address_data(address) -> DvvAddressInfo | None:
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


def _build_apartment_string(address_data: dict) -> str:
    letter = address_data.get("huoneistokirjain", "")
    number = address_data.get("huoneistonumero", "")
    # "000" means no apartment number
    if number and number != "000":
        number = str(int(number))  # strip leading zeros
    else:
        number = ""
    suffix = address_data.get("jakokirjain", "")
    return f"{letter}{number}{suffix}".strip()


def format_address(address_data) -> DvvAddressInfo:
    street_name = ""
    if address_data.get("katunimi", {}).get("fi") is not None:
        street_name = address_data["katunimi"]["fi"]

    street_name_sv = ""
    if address_data.get("katunimi", {}).get("sv") is not None:
        street_name_sv = address_data["katunimi"]["sv"]

    street_number = ""
    if address_data.get("katunumero") is not None:
        street_number = address_data["katunumero"]

    # Note that DVV returns city names in uppercase, capitalize()
    # makes all but the first letter lowercase.
    city = ""
    if address_data.get("postitoimipaikka", {}).get("fi") is not None:
        city = address_data["postitoimipaikka"]["fi"].capitalize()

    city_sv = ""
    if address_data.get("postitoimipaikka", {}).get("sv") is not None:
        city_sv = address_data["postitoimipaikka"]["sv"].capitalize()

    postal_code = ""
    if address_data.get("postinumero") is not None:
        postal_code = address_data["postinumero"]

    address_detail = get_address_details(street_name, street_number)

    # New DVV-API does not differentiate between finnish and swedish
    # apartment data as they're provided in separate fields from the
    # address in contrast to the old API.
    apartment = apartment_sv = _build_apartment_string(address_data)

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
        "city": city,
        "city_sv": city_sv,
        "postal_code": postal_code,
        "zone": zone,
    }


def is_valid_address(address):
    address_valid = (
        address
        and address.get("katunimi", {}).get("fi")
        and address.get("postitoimipaikka", {}).get("fi")
    )
    return address_valid and is_valid_city(
        address.get("postitoimipaikka", {}).get("fi")
    )


def get_person_data_by_data_groups(
    response_data, *, force_single_person=True
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """
    Helper method for parsing data groups from DVV-response, which
    the API returns as a list of dicts with the name of the data group
    under 'tietoryhma'-key.

    Noteworthily, some of the data groups specified in the request
    payload may NOT be included in the response.
    """

    if "perustiedot" not in response_data:
        logger.error("Expected 'perustiedot' in DVV response")
        return None

    if len(response_data["perustiedot"]) == 0:
        logger.error("Expected at least one person info in DVV response")
        return None

    if force_single_person and len(response_data.get("perustiedot", [])) > 1:
        raise ValueError("Expected exactly one person info in DVV response")

    person_data_from_response = response_data["perustiedot"]

    person_data = []
    for data_for_person in person_data_from_response:
        person_info = {}
        for response_data_group in data_for_person["tietoryhmat"]:
            data_group_name = response_data_group["tietoryhma"]
            person_info[data_group_name] = {
                key: value
                for key, value in response_data_group.items()
                if key != "tietoryhma"
            }
        person_data.append(person_info)

    return person_data[0] if force_single_person else person_data


def get_person_info(national_id_number) -> DvvPersonInfo | None:
    logger.info(f"Retrieving person info with national_id_number: {national_id_number}")
    data = get_request_data(national_id_number)
    headers = get_request_headers()
    response = requests.post(
        settings.DVV_PERSONAL_INFO_URL,
        data=json.dumps(data, default=str),
        headers=headers,
        verify=settings.DVV_VERIFY_SSL,
    )
    if not response.ok:
        logger.error(
            f"Invalid DVV response for {national_id_number}. Response: {response.text}"
        )
        return None

    response_data = response.json()

    if "perustiedot" not in response_data:
        logger.error("Expected 'perustiedot' in DVV response")
        return None

    # DVV does not return a 404 code if the given hetu
    # is not found, so we need to check the response
    # content
    if not len(response_data["perustiedot"]):
        logger.error("Expected at least one person info in DVV response")
        return None

    person_info = get_person_data_by_data_groups(response_data)
    if not person_info:
        logger.error(f"Person info not found: {national_id_number}")
        return None

    person_name_info = person_info.get(DATA_GROUP_PERSON_NAME)
    first_name = last_name = ""
    if person_name_info:
        first_name = person_name_info["etunimi"]
        last_name = person_name_info["sukunimi"]

    primary_address, primary_apartment = None, ""
    permanent_address = person_info.get(DATA_GROUP_PERMANENT_ADDRESS)

    if is_valid_address(permanent_address):
        primary_address = format_address(permanent_address)
        primary_apartment = primary_address.get("apartment", "")

    other_address, other_apartment = None, ""
    temporary_address = person_info.get(DATA_GROUP_TEMPORARY_ADDRESS)

    if is_valid_address(temporary_address):
        other_address = format_address(temporary_address)
        other_apartment = other_address.get("apartment", "")

    # Based on the test cases of the muutokset-API (changes), it seems
    # like perustiedot-API only returns the address security ban info
    # in the response if the ban is active.
    address_security_ban = person_info.get(DATA_GROUP_ADDRESS_SECURITY_BAN, {}).get(
        "turvakieltoAktiivinen", False
    )

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
        "address_security_ban": address_security_ban,
        "driver_license_checked": False,
        "active_permits": active_permits,
    }
