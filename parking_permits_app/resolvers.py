from ariadne import (
    MutationType,
    QueryType,
    convert_kwargs_to_snake_case,
    load_schema_from_path,
)
from ariadne.contrib.federation import FederatedObjectType
from django.forms.models import model_to_dict

from project.settings import BASE_DIR

from .models import Address, Customer, ParkingPermit
from .pricing.engine import calculate_cart_item_total_price
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


@query.field("getPermits")
@convert_kwargs_to_snake_case
def resolve_customer_permits(obj, info, customer_id):
    try:
        permits = ParkingPermit.objects.filter(customer__pk=customer_id)
        payload = {
            "success": True,
            "permits": [serialize_permit(permit) for permit in permits],
        }
    except AttributeError:  # todo not found
        payload = {"success": False, "errors": ["Permits item matching {id} not found"]}
    return payload


def serialize_permit(permit):
    price = permit.parking_zone.get_current_price()
    vehicle = permit.vehicle
    offer = calculate_cart_item_total_price(
        item_price=price,
        item_quantity=1,
        vehicle_is_secondary=permit.primary_vehicle is False,
        vehicle_is_low_emission=vehicle.is_low_emission(),
    )
    contract_type = permit.contract_type
    return snake_to_camel_dict(
        {
            "id": permit.pk,
            **model_to_dict(permit),
            "price": {
                "original": price,
                "offer": offer,
                "currency": "€",
            },
            "vehicle": {
                "id": vehicle.pk,
                "vehicle_type": {"id": vehicle.type.id, **model_to_dict(vehicle.type)},
                **model_to_dict(vehicle),
            },
            "contract": {"id": contract_type.pk, **model_to_dict(contract_type)},
        }
    )


@query.field("profile")
def resolve_user_profile(_, info, *args):
    profile = HelsinkiProfile(info.context["request"])
    customer = profile.get_customer()
    primary_address, other_address = profile.get_addresses()

    primary_obj, _ = Address.objects.update_or_create(
        id=primary_address.get("id"), defaults=primary_address
    )

    other_obj, _ = Address.objects.update_or_create(
        id=other_address.get("id"), defaults=other_address
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
                **model_to_dict(primary_obj.zone),
                "shared_product_id": primary_obj.zone.shared_product_id,
                "id": primary_obj.zone.pk,
            },
        },
        "other_address": {
            **model_to_dict(other_obj),
            "id": other_obj.pk,
            "zone": {
                **model_to_dict(other_obj.zone),
                "shared_product_id": primary_obj.zone.shared_product_id,
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
