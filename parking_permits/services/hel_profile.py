import requests
from ariadne import load_schema_from_path
from django.conf import settings

from parking_permits.models.common import SourceSystem
from parking_permits.services.kmo import parse_street_name_and_number
from project.settings import BASE_DIR

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
        addresses = self.__profile.get("addresses")
        if not addresses:
            return None, None
        return self._extract_addresses(addresses)

    def _extract_addresses(self, addresses):
        if not self.__profile:
            self._get_profile()
        primary_address = None
        other_address = None
        for address in addresses.get("edges"):
            address_node = address.get("node")
            if address_node:
                parsed_address = parse_street_name_and_number(
                    address_node.get("address")
                )
                data = {
                    "street_name": parsed_address.get("street_name"),
                    "street_number": parsed_address.get("street_number"),
                    "city": address_node.get("city"),
                    "postal_code": address_node.get("postalCode"),
                }
                if address_node.get("primary"):
                    primary_address = data
                else:
                    other_address = data
        return primary_address, other_address

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
