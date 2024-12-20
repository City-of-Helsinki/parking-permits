import logging

import requests
from ariadne import load_schema_from_path
from django.conf import settings

from parking_permits.models.common import SourceSystem
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
        verified_info = self.__profile.get("verifiedPersonalInformation")
        national_id_number = (
            verified_info.get("nationalIdentificationNumber") if verified_info else None
        )
        first_name = verified_info.get("firstName") if verified_info else None
        last_name = verified_info.get("lastName") if verified_info else None
        return {
            "source_system": SourceSystem.HELSINKI_PROFILE,
            "source_id": self.__profile.get("id"),
            "first_name": first_name,
            "last_name": last_name,
            "email": email_node.get("email") if email_node else None,
            "phone_number": phone_node.get("phone") if phone_node else None,
            "national_id_number": national_id_number,
        }

    def _get_profile(self):
        api_token = self.request.headers.get("X-Authorization")
        response = requests.post(
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
