import base64
import json
import logging
import re

import requests
from django.conf import settings

from parking_permits.exceptions import DVVIntegrationError

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


def parse_address(address):
    """
    Parse an address string and return the street name and street number

    The first spaced number is considered as the street number, and the
    sub-string before the number is considered as the street name
    """
    m = re.search(r"(.+?)\s(\d+)", address)
    if not m:
        logger.error(f"Cannot parse address: {address}")
        raise DVVIntegrationError("Parsing address error")
    return m.group(1), m.group(2)


def format_address(address_data):
    # DVV combines the street name, street number and apartment
    # building number together in a single string. We only need
    # to use the street name and street number

    street_name, street_number = parse_address(address_data["LahiosoiteS"])
    return {
        "street_name": street_name,
        "street_number": street_number,
        "city": "Helsinki",
        "city_sv": "Helsingfors",
        "postal_code": address_data["Postinumero"],
    }


def is_valid_address(address):
    return (
        address["LahiosoiteS"] != ""
        and address["PostitoimipaikkaS"]
        and address["PostitoimipaikkaS"].upper() == "HELSINKI"
    )


def get_person_info(hetu):
    data = get_request_data(hetu)
    headers = get_request_headers()
    response = requests.post(
        settings.DVV_PERSONAL_INFO_URL,
        json.dumps(data),
        headers=headers,
    )
    if not response.ok:
        logger.error(f"Invalid DVV response for {hetu}. Response: {response.text}")
        return None

    response_data = response.json()
    # DVV does not return a 404 code if the given hetu
    # is not found, so we need to check the response
    # content
    person_info = response_data.get("Henkilo")
    if not person_info:
        logger.error(f"Person info not found: {hetu}")
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
        "national_id_number": hetu,
        "first_name": first_name,
        "last_name": last_name,
        "primary_address": primary_address,
        "other_address": other_address,
    }
