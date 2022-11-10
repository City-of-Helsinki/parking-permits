import logging
import re

import requests
import xmltodict
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.utils.translation import gettext_lazy as _
from rest_framework import status

from parking_permits.exceptions import AddressError
from parking_permits.models.address import Address

logger = logging.getLogger("db")


def get_wfs_result(street_name="", street_number_token=""):
    street_number_first_part = re.search(r"^\d+", street_number_token)
    street_number = (
        int(street_number_first_part.group()) if street_number_first_part else 0
    )
    # escape single quotes
    street_name = street_name.replace("'", r"&#39")

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

    response = requests.get(settings.KMO_URL, params=params)

    if response.status_code != status.HTTP_200_OK:
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


def parse_street_name_and_number(street_address):
    match = re.search(r"\D+", street_address)
    street_name = match.group().strip() if match else street_address
    street_number = street_address[match.end() :].strip() if match else ""

    return dict(
        street_name=street_name,
        street_number=street_number,
    )


def get_address_from_db(street_name, street_number):
    address_qs = Address.objects.filter(
        street_name=street_name, street_number=street_number
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
