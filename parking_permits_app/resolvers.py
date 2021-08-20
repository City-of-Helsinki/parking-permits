from ariadne import MutationType, QueryType, convert_kwargs_to_snake_case
from ariadne.contrib.federation import FederatedObjectType
from django.contrib.auth import get_user_model

from .services.kmo import get_wfs_result, parse_street_name_and_number

query = QueryType()
mutation = MutationType()
address_node = FederatedObjectType("AddressNode")

schema_bindables = [
    query,
    mutation,
    address_node,
]


@query.field("admin_email")
def resolve_admin_email(*args):
    return get_user_model().objects.get(username="admin").email


@mutation.field("createParkingPermit")
def resolve_create_parking_permit(obj, info, input):
    return {
        "parkingPermit": {
            "identifier": 8000000,
            "status": input.get("status"),
            "contractType": "FIXED_PERIOD",
        }
    }


@mutation.field("updateParkingPermit")
@convert_kwargs_to_snake_case
def resolve_update_parking_permit(obj, info, parking_permit, input):
    return {
        "parkingPermit": {
            "identifier": 8000000,
            "status": input.get("status"),
            "contractType": "FIXED_PERIOD",
        }
    }


@address_node.field("locationData")
def resolve_location_data(addresss_node_obj, info):
    street_address = addresss_node_obj.get("address")
    data = get_wfs_result(**parse_street_name_and_number(street_address))

    address_data = data.get("features")[1]
    zone_data = data.get("features")[0]

    address_location = address_data.get("geometry").get("coordinates")
    zone_id = zone_data.get("properties").get("asukaspysakointitunnus")
    zone_name = zone_data.get("properties").get("alueen_nimi")
    zone_area = zone_data.get("geometry").get("coordinates")

    return {
        "addressLocation": address_location,
        "zoneId": zone_id,
        "zoneName": zone_name,
        "zoneArea": zone_area,
    }
