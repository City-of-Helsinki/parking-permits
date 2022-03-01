from ariadne import (
    MutationType,
    QueryType,
    convert_kwargs_to_snake_case,
    load_schema_from_path,
    snake_case_fallback_resolvers,
)
from ariadne.contrib.federation import FederatedObjectType
from django.db.utils import IntegrityError

from project.settings import BASE_DIR

from .customer_permit import CustomerPermit
from .decorators import is_authenticated
from .models import Address, Customer, ParkingZone, Vehicle
from .models.order import Order
from .models.parking_permit import ParkingPermit, ParkingPermitStatus
from .services.hel_profile import HelsinkiProfile
from .services.kmo import get_address_detail_from_kmo
from .talpa.order import TalpaOrderManager

helsinki_profile_query = load_schema_from_path(
    BASE_DIR / "parking_permits" / "schema" / "helsinki_profile.graphql"
)


query = QueryType()
mutation = MutationType()
address_node = FederatedObjectType("AddressNode")
profile_node = FederatedObjectType("ProfileNode")

schema_bindables = [query, mutation, address_node, snake_case_fallback_resolvers]

ACTIVE_PERMIT_STATUSES = [
    ParkingPermitStatus.DRAFT,
    ParkingPermitStatus.VALID,
]


@query.field("getPermits")
@is_authenticated
@convert_kwargs_to_snake_case
def resolve_customer_permits(obj, info):
    request = info.context["request"]
    return get_customer_permits(request.user.customer.id)


@query.field("profile")
@is_authenticated
def resolve_user_profile(_, info, *args):
    request = info.context["request"]
    profile = HelsinkiProfile(request)
    customer = profile.get_customer()
    primary_address, other_address = profile.get_addresses()

    primary_street_name = primary_address.get("street_name")
    primary_street_number = primary_address.get("street_number")
    primary_address_detail = get_address_detail_from_kmo(
        primary_street_name, primary_street_number
    )
    primary_address.update(primary_address_detail)
    zone = ParkingZone.objects.get_for_location(primary_address["location"])
    primary_address["zone"] = zone
    primary_obj, _ = Address.objects.update_or_create(
        source_system=primary_address.get("source_system"),
        source_id=primary_address.get("source_id"),
        defaults=primary_address,
    )

    other_street_name = primary_address.get("street_name")
    other_street_number = primary_address.get("street_number")
    other_address_detail = get_address_detail_from_kmo(
        other_street_name, other_street_number
    )
    other_address.update(other_address_detail)
    zone = ParkingZone.objects.get_for_location(other_address["location"])
    other_address["zone"] = zone
    other_obj, _ = Address.objects.update_or_create(
        source_system=other_address.get("source_system"),
        source_id=other_address.get("source_id"),
        defaults=other_address,
    )

    customer_obj, _ = Customer.objects.update_or_create(
        source_system=customer.get("source_system"),
        source_id=customer.get("source_id"),
        defaults={
            "user": request.user,
            **customer,
            **{"primary_address": primary_obj, "other_address": other_obj},
        },
    )

    return customer_obj


@mutation.field("deleteParkingPermit")
@is_authenticated
@convert_kwargs_to_snake_case
def resolve_delete_parking_permit(obj, info, permit_id):
    request = info.context["request"]
    return {"success": CustomerPermit(request.user.customer.id).delete(permit_id)}


@mutation.field("createParkingPermit")
@is_authenticated
@convert_kwargs_to_snake_case
def resolve_create_parking_permit(obj, info, zone_id):
    request = info.context["request"]
    CustomerPermit(request.user.customer.id).create(zone_id)
    return get_customer_permits(request.user.customer.id)


@mutation.field("updateParkingPermit")
@is_authenticated
@convert_kwargs_to_snake_case
def resolve_update_parking_permit(obj, info, input, permit_id=None):
    request = info.context["request"]
    CustomerPermit(request.user.customer.id).update(input, permit_id)
    return get_customer_permits(request.user.customer.id)


@mutation.field("updateVehicle")
@is_authenticated
@convert_kwargs_to_snake_case
def resolve_update_vehicle(obj, info, vehicle_id, registration):
    vehicle = Vehicle.objects.get(id=vehicle_id)
    vehicle.registration_number = registration.upper()
    try:
        vehicle.save(update_fields=["registration_number"])
        return {"success": True, "vehicle": vehicle}
    except IntegrityError:
        return {
            "success": False,
            "errors": [
                f"Permit with registration {vehicle.registration_number} already exist."
            ],
        }


@mutation.field("endParkingPermit")
@is_authenticated
@convert_kwargs_to_snake_case
def resolve_end_permit(_, info, permit_ids, end_type, iban=None):
    request = info.context["request"]
    return {
        "success": CustomerPermit(request.user.customer.id).end(
            permit_ids, end_type, iban
        )
    }


def get_customer_permits(customer_id):
    return {
        "success": True,
        "permits": CustomerPermit(customer_id).get(),
    }


@mutation.field("createOrder")
@is_authenticated
def resolve_create_order(_, info):
    customer = info.context["request"].user.customer
    permits = ParkingPermit.objects.filter(
        customer=customer, status=ParkingPermitStatus.DRAFT
    )
    order = Order.objects.create_for_permits(permits)
    checkout_url = TalpaOrderManager.send_to_talpa(order)
    return {"success": True, "order": {"checkout_url": checkout_url}}
