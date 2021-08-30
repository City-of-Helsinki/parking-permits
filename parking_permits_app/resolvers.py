from ariadne import (
    MutationType,
    QueryType,
    convert_kwargs_to_snake_case,
    load_schema_from_path,
)
from ariadne.contrib.federation import FederatedObjectType
from django.forms.models import model_to_dict

from project.settings import BASE_DIR

from .models import Address, Customer
from .services.hel_profile import HelsinkiProfile

helsinki_profile_query = load_schema_from_path(
    BASE_DIR / "parking_permits_app" / "schema" / "helsinki_profile.graphql"
)


query = QueryType()
mutation = MutationType()
address_node = FederatedObjectType("AddressNode")
profile_node = FederatedObjectType("ProfileNode")

schema_bindables = [
    query,
    mutation,
    address_node,
]


@query.field("profile")
def resolve_user_profile(_, info, *args):
    profile = HelsinkiProfile(info.context["request"])
    customer = profile.get_customer()
    primary_address, other_address = profile.get_addresses()

    primary_obj, _ = Address.objects.update_or_create(
        id=primary_address.get("id"), defaults=primary_address
    )

    other_obj, _ = Address.objects.update_or_create(
        id=primary_address.get("id"), defaults=other_address
    )

    customer_obj, _ = Customer.objects.update_or_create(
        id=customer.get("id"),
        defaults={
            **customer,
            **{"primary_address": primary_obj, "other_address": other_obj},
        },
    )

    # TODO: Handle the errors for non existing objects
    customer_dict = {
        **model_to_dict(customer_obj),
        "id": customer_obj.pk,
        "primary_address": {
            **model_to_dict(primary_obj),
            "id": primary_obj.pk,
            "zone": {
                **model_to_dict(other_obj.zone),
                "id": other_obj.zone.pk,
            },
        },
        "other_address": {
            **model_to_dict(other_obj),
            "id": other_obj.pk,
            "zone": {
                **model_to_dict(other_obj.zone),
                "id": other_obj.zone.pk,
            },
        },
    }

    return snake_to_camel_dict(customer_dict)


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


@profile_node.field("userId")
def resolve_user_id(profile_obj, info):
    return {
        "userId": profile_obj.get("id"),
    }


def snake_to_camel_dict(dictionary):
    res = dict()
    for key in dictionary.keys():
        if isinstance(dictionary[key], dict):
            res[camel_str(key)] = snake_to_camel_dict(dictionary[key])
        else:
            res[camel_str(key)] = dictionary[key]
    return res


def camel_str(snake_str):
    first, *others = snake_str.split("_")
    return "".join([first.lower(), *map(str.title, others)])
