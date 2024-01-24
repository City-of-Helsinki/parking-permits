import logging
import re

import requests
import xmltodict
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from parking_permits.exceptions import AddressError
from parking_permits.models import ParkingZone
from parking_permits.models.address import Address

logger = logging.getLogger("db")


def get_wfs_result(street_name="", street_number_token=""):
    street_number_first_part = re.search(r"^\d+", street_number_token)
    street_number = (
        int(street_number_first_part.group()) if street_number_first_part else 0
    )

    # escape single quotes: we need to use 4x the quote because the
    # value is inside double quotes
    # see https://docs.geoserver.org/main/en/user/filter/ecql_reference.html#filter-ecql-reference
    street_name = street_name.replace("'", "''''")

    street_address = f"katunimi=''{street_name}'' AND osoitenumero=''{street_number}''"
    query_single_args = [
        "'avoindata:Helsinki_osoiteluettelo'",
        "'geom'",
        f"'{street_address}'",
    ]
    cql_filter = f"CONTAINS(geom,querySingle({','.join(query_single_args)}))"

    type_names = [
        "avoindata:Asukas_ja_yrityspysakointivyohykkeet_alue",
        "avoindata:Helsinki_osoiteluettelo",
    ]

    params = {
        "CQL_FILTER": cql_filter,
        "OUTPUTFORMAT": "json",
        "REQUEST": "GetFeature",
        "SERVICE": "WFS",
        "srsName": "EPSG:4326",
        "TYPENAME": ",".join(type_names),
        "VERSION": "2.0.0",
    }

    response = requests.get(settings.KAMI_URL, params=params)

    if response.status_code != 200:
        xml_response = xmltodict.parse(response.content)

        error_message = (
            xml_response.get("ows:ExceptionReport", dict())
            .get("ows:Exception", dict())
            .get("ows:ExceptionText", "Unknown Error")
        )
        raise Exception(error_message)

    result = response.json()

    result_features = [
        feature
        for feature in result.get("features")
        if not (
            feature.get("geometry").get("type") == "Point"
            and feature.get("properties").get("katunimi") != street_name
        )
    ]

    return {**result, "features": result_features}


def search_address(search_text):
    if not search_text:
        return []
    street_name, street_number, __ = parse_street_data(search_text)

    cql_filter = (
        f"katunimi ILIKE '{street_name}%' AND osoitenumero='{street_number}'"
        if street_number
        else f"katunimi ILIKE '{street_name}%'"
    )
    params = {
        "CQL_FILTER": cql_filter,
        "OUTPUTFORMAT": "json",
        "REQUEST": "GetFeature",
        "SERVICE": "WFS",
        "srsName": "EPSG:4326",
        "TYPENAMES": "avoindata:Helsinki_osoiteluettelo",
        "VERSION": "2.0.0",
        "COUNT": "8",
    }
    response = requests.get(settings.KAMI_URL, params=params)

    if response.status_code != 200:
        xml_response = xmltodict.parse(response.content)

        error_message = (
            xml_response.get("ows:ExceptionReport", dict())
            .get("ows:Exception", dict())
            .get("ows:ExceptionText", "Unknown Error")
        )
        raise Exception(error_message)

    result = response.json()

    if not result.get("features"):
        return Address.objects.filter(
            Q(street_name__icontains=street_name)
            | Q(street_name_sv__icontains=street_name)
            | Q(street_number__icontains=street_number)
        )

    parsed_addresses = []
    for feature in result.get("features"):
        if feature.get("geometry").get("type") == "Point":
            parsed_address = parse_feature(feature)
            if parsed_address.get("zone"):
                parsed_addresses.append(parsed_address)

    return parsed_addresses


def parse_feature(feature):
    properties = feature.get("properties", {})
    geometry = feature.get("geometry", {})
    location = GEOSGeometry(str(geometry))
    try:
        zone = ParkingZone.objects.get_for_location(location)
    except ParkingZone.DoesNotExist:
        zone = None
    return dict(
        street_name=properties.get("katunimi", ""),
        street_name_sv=properties.get("gatan", ""),
        street_number=properties.get("osoitenumero_teksti", ""),
        postal_code=properties.get("postinumero", ""),
        city=properties.get("kaupunki", "").upper(),
        city_sv=properties.get("staden", "").upper(),
        location=location,
        zone=zone,
    )


def extract_street_number_and_apartment(street_data):
    parts = street_data.split()
    if not parts:
        return "", ""
    street_number = parts[0].strip()
    apartment = " ".join(parts[1:]).strip()
    return street_number, apartment


def parse_street_data(street_address: str) -> tuple[str, str, str]:
    match = re.search(r"\D+", street_address)
    street_name = match.group().strip() if match else street_address
    street_number, apartment = extract_street_number_and_apartment(
        street_address[match.end() :].strip() if match else ""
    )
    return street_name, street_number, apartment


def get_address_from_db(street_name, street_number):
    address_qs = Address.objects.filter(
        street_name=street_name, street_number__istartswith=street_number
    )
    if address_qs.exists():
        return address_qs.first()


def get_address_details(street_name, street_number):
    results = get_wfs_result(street_name, street_number)
    features = results.get("features")
    if not features:
        address = get_address_from_db(street_name, street_number)
        if address:
            return {
                "location": address.location.centroid,
            }
        logger.error("Not a valid customer address")
        raise AddressError(_("Not a valid customer address"))
    address_feature = next(
        feature
        for feature in features
        if feature.get("geometry").get("type") == "Point"
    )
    location = GEOSGeometry(str(address_feature.get("geometry")))
    return {
        "location": location,
    }
