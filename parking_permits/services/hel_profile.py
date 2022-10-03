import logging

import requests
from ariadne import load_schema_from_path
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from parking_permits.exceptions import ObjectNotFound
from parking_permits.models.common import SourceSystem
from parking_permits.services.dvv import get_person_info
from project.settings import BASE_DIR

logger = logging.getLogger("db")

helsinki_profile_query = load_schema_from_path(
    BASE_DIR / "parking_permits" / "schema" / "helsinki_profile.graphql"
)


class InvalidApiToken(Exception):
    pass


class HelsinkiProfile:
    __profile = None

    def __init__(self, request):
        self.request = request

    def get_customer(self):
        if not self.__profile:
            self._get_profile()

        email_node = self.__profile.get("primaryEmail")
        phone_node = self.__profile.get("primaryPhone")
        return {
            "source_system": SourceSystem.HELSINKI_PROFILE,
            "source_id": self.__profile.get("id"),
            "first_name": self.__profile.get("firstName"),
            "last_name": self.__profile.get("lastName"),
            "email": email_node.get("email") if email_node else None,
            "phone_number": phone_node.get("phone") if phone_node else None,
            "national_id_number": self.__profile.get(
                "verifiedPersonalInformation", {}
            ).get("nationalIdentificationNumber"),
        }

    def get_addresses(self):
        if not self.__profile:
            self._get_profile()
        primary_address, other_address = None, None
        national_id_number = self.__profile.get("verifiedPersonalInformation", {}).get(
            "nationalIdentificationNumber"
        )
        if national_id_number:
            logger.info("Retrieving customer addresses from DVV...")
            customer = get_person_info(national_id_number)
            if not customer:
                raise ObjectNotFound(_("Person not found"))
            primary_address_data = customer.get("primary_address")
            if primary_address_data:
                primary_address = self._extract_dvv_address(primary_address_data)
            other_address_data = customer.get("other_address")
            if other_address_data:
                other_address = self._extract_dvv_address(other_address_data)
        return primary_address, other_address

    def _extract_dvv_address(self, address):
        other_address = {
            "street_name": address.get("street_name"),
            "street_number": address.get("street_number"),
            "city": address.get("city"),
            "postal_code": address.get("postal_code"),
        }
        return other_address

    def _get_profile(self):
        api_token = self.request.headers.get("X-Authorization")
        response = requests.get(
            settings.OPEN_CITY_PROFILE_GRAPHQL_API,
            json={"query": helsinki_profile_query},
            headers={"Authorization": api_token},
        )
        data = response.json()
        if data.get("errors"):
            message = next(iter(data.get("errors"))).get("message")
            raise InvalidApiToken(message)
        self._extract_profile(response.json())

    def _extract_profile(self, hel_raw_data):
        data = hel_raw_data.get("data")
        if data:
            self.__profile = data.get("myProfile")
