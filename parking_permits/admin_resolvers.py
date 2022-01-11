import logging

import reversion
from ariadne import (
    MutationType,
    ObjectType,
    QueryType,
    convert_kwargs_to_snake_case,
    snake_case_fallback_resolvers,
)
from dateutil.parser import isoparse
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from parking_permits.models import (
    Address,
    Customer,
    ParkingPermit,
    ParkingZone,
    Product,
    Vehicle,
)

from .decorators import is_ad_admin
from .exceptions import ObjectNotFound, UpdatePermitError
from .models.parking_permit import ContractType
from .paginator import QuerySetPaginator
from .reversion import EventType, get_obj_changelogs, get_reversion_comment
from .services.kmo import get_address_detail_from_kmo
from .utils import apply_filtering, apply_ordering, get_end_time

logger = logging.getLogger("db")

query = QueryType()
mutation = MutationType()
PermitDetail = ObjectType("PermitDetailNode")
schema_bindables = [query, mutation, PermitDetail, snake_case_fallback_resolvers]


@query.field("permits")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_permits(obj, info, page_input, order_by=None, search_items=None):
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
def resolve_permit_detail(obj, info, permit_id):
    return ParkingPermit.objects.get(identifier=permit_id)


@PermitDetail.field("changeLogs")
def resolve_permit_detail_history(permit, info):
    return get_obj_changelogs(permit)


@query.field("zones")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_zones(obj, info):
    return ParkingZone.objects.all().order_by("name")


@query.field("customer")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_customer(obj, info, national_id_number):
    try:
        customer = Customer.objects.get(national_id_number=national_id_number)
    except Customer.DoesNotExist:
        logger.info("Customer does not exist, search from DVV")
        # TODO: search from DVV and create customer once DVV integration is ready
        raise ObjectNotFound(_("Customer not found"))
    return customer


@query.field("vehicle")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_vehicle(obj, info, reg_number, national_id_number):
    try:
        q = Q(registration_number=reg_number) & (
            Q(owner__national_id_number=national_id_number)
            | Q(holder__national_id_number=national_id_number)
        )
        vehicle = Vehicle.objects.get(q)
    except Vehicle.DoesNotExist:
        logger.info("Vehicle does not exist, search from Traficom")
        # TODO: search from Traficom and create vehicle once Traficom integration is ready
        raise ObjectNotFound(_("Vehicle not found for the customer"))

    return vehicle


def update_or_create_customer(customer_info):
    if customer_info["address_security_ban"]:
        customer_info.pop("first_name", None)
        customer_info.pop("last_name", None)
        customer_info.pop("address", None)

    customer_data = {
        "first_name": customer_info.get("first_name", ""),
        "last_name": customer_info.get("last_name", ""),
        "national_id_number": customer_info["national_id_number"],
        "email": customer_info["email"],
        "phone_number": customer_info["phone_number"],
        "address_security_ban": customer_info["address_security_ban"],
        "driver_license_checked": customer_info["driver_license_checked"],
    }

    address_info = customer_info.get("address")
    if address_info:
        kmo_address_detail = get_address_detail_from_kmo(
            address_info["street_name"], address_info["street_number"]
        )
        zone = ParkingZone.objects.get_for_location(kmo_address_detail["location"])
        address = Address.objects.create(
            street_name=address_info["street_name"],
            street_name_sv=kmo_address_detail["street_name_sv"],
            street_number=address_info["street_number"],
            city=address_info["city"],
            city_sv=kmo_address_detail["city_sv"],
            location=kmo_address_detail["location"],
            zone=zone,
            primary=True,
        )
        customer_data["primary_address"] = address
    else:
        customer_data["primary_address"] = None
    return Customer.objects.update_or_create(
        national_id_number=customer_info["national_id_number"], defaults=customer_data
    )[0]


def update_or_create_vehicle(vehicle_info):
    vehicle_data = {
        "registration_number": vehicle_info["registration_number"],
        "manufacturer": vehicle_info["manufacturer"],
        "model": vehicle_info["model"],
        "low_emission_vehicle": vehicle_info["is_low_emission"],
        "consent_low_emission_accepted": vehicle_info["consent_low_emission_accepted"],
        "serial_number": vehicle_info["serial_number"],
        "category": vehicle_info["category"],
    }
    return Vehicle.objects.update_or_create(
        registration_number=vehicle_info["registration_number"], defaults=vehicle_data
    )[0]


@mutation.field("createResidentPermit")
@is_ad_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_create_resident_permit(obj, info, permit):
    customer_info = permit["customer"]
    customer = update_or_create_customer(customer_info)

    vehicle_info = permit["vehicle"]
    vehicle = update_or_create_vehicle(vehicle_info)

    parking_zone = ParkingZone.objects.get(name=customer_info["zone"])
    with reversion.create_revision():
        start_time = isoparse(permit["start_time"])
        end_time = get_end_time(start_time, permit["month_count"])
        permit = ParkingPermit.objects.create(
            contract_type=ContractType.FIXED_PERIOD,
            customer=customer,
            vehicle=vehicle,
            parking_zone=parking_zone,
            status=permit["status"],
            start_time=start_time,
            month_count=permit["month_count"],
            end_time=end_time,
        )
        request = info.context["request"]
        reversion.set_user(request.user)
        comment = get_reversion_comment(EventType.CREATED, permit)
        reversion.set_comment(comment)
    return {"success": True}


@mutation.field("updateResidentPermit")
@is_ad_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_update_resident_permit(obj, info, permit_id, permit_info):
    try:
        permit = ParkingPermit.objects.get(identifier=permit_id)
    except ParkingPermit.DoesNotExist:
        raise ObjectNotFound(_("Parking permit not found"))

    customer_info = permit_info["customer"]
    if permit.customer.national_id_number != customer_info["national_id_number"]:
        raise UpdatePermitError(_("Cannot change the customer of the permit"))
    update_or_create_customer(customer_info)

    vehicle_info = permit_info["vehicle"]
    vehicle = update_or_create_vehicle(vehicle_info)

    parking_zone = ParkingZone.objects.get(name=customer_info["zone"])
    with reversion.create_revision():
        permit.status = permit_info["status"]
        permit.parking_zone = parking_zone
        permit.vehicle = vehicle
        permit.save()
        request = info.context["request"]
        reversion.set_user(request.user)
        comment = get_reversion_comment(EventType.CHANGED, permit)
        reversion.set_comment(comment)
    return {"success": True}


@mutation.field("endPermit")
@is_ad_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_end_permit(obj, info, permit_id, end_type, iban=None):
    request = info.context["request"]
    with reversion.create_revision():
        permit = ParkingPermit.objects.get(identifier=permit_id)
        permit.end_permit(end_type)

        if permit.contract_type == ContractType.OPEN_ENDED:
            permit.end_subscription()
        elif (
            permit.contract_type == ContractType.FIXED_PERIOD and not permit.has_refund
        ):
            permit.create_refund(iban)

        reversion.set_user(request.user)
        comment = get_reversion_comment(EventType.CHANGED, permit)
        reversion.set_comment(comment)

    return {"success": True}


@query.field("products")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_products(obj, info, page_input, order_by=None, search_items=None):
    products = Product.objects.all().order_by("zone__name")
    if order_by:
        products = apply_ordering(products, order_by)
    if search_items:
        products = apply_filtering(products, search_items)
    paginator = QuerySetPaginator(products, page_input)
    return {
        "page_info": paginator.page_info,
        "objects": paginator.object_list,
    }


@query.field("product")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_product(obj, info, product_id):
    return Product.objects.get(id=product_id)


@mutation.field("updateProduct")
@is_ad_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_update_product(obj, info, product_id, product):
    request = info.context["request"]
    zone = ParkingZone.objects.get(name=product["zone"])
    _product = Product.objects.get(id=product_id)
    _product.type = product["type"]
    _product.zone = zone
    _product.unit_price = product["unit_price"]
    _product.unit = product["unit"]
    _product.start_date = product["start_date"]
    _product.end_date = product["end_date"]
    _product.vat_percentage = product["vat_percentage"]
    _product.low_emission_discount = product["low_emission_discount"]
    _product.modified_by = request.user
    _product.save()
    return {"success": True}


@mutation.field("deleteProduct")
@is_ad_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_delete_product(obj, info, product_id):
    product = Product.objects.get(id=product_id)
    product.delete()
    return {"success": True}


@mutation.field("createProduct")
@is_ad_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_create_product(obj, info, product):
    request = info.context["request"]
    zone = ParkingZone.objects.get(name=product["zone"])
    Product.objects.create(
        type=product["type"],
        zone=zone,
        unit_price=product["unit_price"],
        unit=product["unit"],
        start_date=product["start_date"],
        end_date=product["end_date"],
        vat=product["vat_percentage"] / 100,
        low_emission_discount=product["low_emission_discount"],
        created_by=request.user,
        modified_by=request.user,
    )
    return {"success": True}
