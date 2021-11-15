from datetime import datetime

import reversion
from ariadne import (
    MutationType,
    ObjectType,
    QueryType,
    convert_kwargs_to_snake_case,
    snake_case_fallback_resolvers,
)
from django.conf import settings
from django.contrib.gis.geos import Point

from parking_permits_app.models import (
    Address,
    Customer,
    ParkingPermit,
    ParkingZone,
    Vehicle,
)

from .constants import ContractType
from .decorators import is_ad_admin
from .paginator import QuerySetPaginator
from .reversion import EventType, get_obj_changelogs, get_reversion_comment
from .utils import apply_filtering, apply_ordering

query = QueryType()
mutation = MutationType()
PermitDetail = ObjectType("PermitDetailNode")
schema_bindables = [query, mutation, PermitDetail, snake_case_fallback_resolvers]


@query.field("permits")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_permits(_, info, page_input, order_by=None, search_items=None):
    permits = ParkingPermit.objects.all()
    if order_by:
        permits = apply_ordering(permits, order_by)
    if search_items:
        permits = apply_filtering(permits, search_items)
    paginator = QuerySetPaginator(permits, page_input)
    return {
        "page_info": paginator.page_info,
        "objects": paginator.object_list,
    }


@query.field("permitDetail")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_permit_detail(_, info, permit_id):
    return ParkingPermit.objects.get(identifier=permit_id)


@PermitDetail.field("changeLogs")
def resolve_permit_detail_history(permit, info):
    return get_obj_changelogs(permit)


@query.field("zones")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_zones(_, info):
    return ParkingZone.objects.all()


@mutation.field("createResidentPermit")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_create_resident_permit(_, info, permit):
    # TODO: Update this once we have proper Traficom and DVV integrations
    # This method relies on the mock data passed in from
    # admin ui and the structure of data will be most
    # likely different from actual data. Note that we
    # also provide a hard coded address location to
    # bypass the reverse geocoding process when saving
    # the address
    customer_info = permit["customer"]
    address_info = customer_info["address"]
    address, _ = Address.objects.update_or_create(
        id=f"{address_info['street_name']} {address_info['street_number']}",
        defaults={
            "street_name": address_info["street_name"],
            "street_name_sv": address_info["street_name_sv"],
            "street_number": address_info["street_number"],
            "city": address_info["city"],
            "city_sv": address_info["city_sv"],
            "postal_code": address_info["postal_code"],
            "location": Point(60.170974, 24.941431, srid=settings.SRID),
            "primary": True,
        },
    )
    customer, _ = Customer.objects.update_or_create(
        id=customer_info["national_id_number"],
        defaults={
            "primary_address": address,
            "first_name": customer_info["first_name"],
            "last_name": customer_info["last_name"],
            "national_id_number": customer_info["national_id_number"],
            "email": customer_info["email"],
            "phone_number": customer_info["phone_number"],
            "address_security_ban": customer_info["address_security_ban"],
            "driver_license_checked": customer_info["driver_license_checked"],
        },
    )
    vehicle_info = permit["vehicle"]
    owner, _ = Customer.objects.update_or_create(
        id=vehicle_info["owner"]["national_id_number"],
        defaults=vehicle_info["owner"],
    )
    holder, _ = Customer.objects.update_or_create(
        id=vehicle_info["holder"]["national_id_number"],
        defaults=vehicle_info["holder"],
    )

    # Currently, the Vehicle registration_number is not unique,
    # which raised exception there're multiple vehicles for the
    # same registration number in the database
    vehicle = Vehicle.objects.filter(
        registration_number=vehicle_info["registration_number"]
    ).first()
    if not vehicle:
        vehicle = Vehicle.objects.create(
            registration_number=vehicle_info["registration_number"],
            production_year=vehicle_info["production_year"],
            manufacturer=vehicle_info["manufacturer"],
            emission=vehicle_info["emission"],
            model=vehicle_info["model"],
            low_emission_vehicle=vehicle_info["is_low_emission"],
            owner=owner,
            holder=holder,
        )
    parking_zone = ParkingZone.objects.get(name=customer_info["zone"]["name"])
    with reversion.create_revision():
        permit = ParkingPermit.objects.create(
            contract_type=ContractType.FIXED_PERIOD.value,
            customer=customer,
            vehicle=vehicle,
            parking_zone=parking_zone,
            status=permit["status"],
            start_time=datetime.strptime(permit["start_time"], "%Y-%m-%dT%H:%M:%S.%fZ"),
            month_count=permit["month_count"],
            consent_low_emission_accepted=vehicle_info["consent_low_emission_accepted"],
        )
        request = info.context["request"]
        reversion.set_user(request.user)
        comment = get_reversion_comment(EventType.CREATED, permit)
        reversion.set_comment(comment)
    return {"success": True}
