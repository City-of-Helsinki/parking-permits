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
from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from parking_permits.models import (
    Address,
    Customer,
    Order,
    ParkingPermit,
    ParkingZone,
    Product,
    Refund,
    Vehicle,
)

from .decorators import is_ad_admin
from .exceptions import ObjectNotFound, ParkingZoneError, RefundError, UpdatePermitError
from .models.parking_permit import ContractType
from .paginator import QuerySetPaginator
from .reversion import EventType, get_obj_changelogs, get_reversion_comment
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


@query.field("zoneByLocation")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_zone_by_location(obj, info, location):
    _location = Point(*location, srid=settings.SRID)
    try:
        return ParkingZone.objects.get_for_location(_location)
    except ParkingZone.DoesNotExist:
        raise ParkingZoneError(_("No parking zone found for the location"))
    except ParkingZone.MultipleObjectsReturned:
        raise ParkingZoneError(_("Multiple parking zones found for the location"))


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

    address_info = customer_info.get("primary_address")
    if address_info:
        location = Point(*address_info["location"], srid=settings.SRID)
        zone = ParkingZone.objects.get_for_location(location)
        address = Address.objects.update_or_create(
            source_system=address_info["source_system"],
            source_id=address_info["source_id"],
            defaults={
                "street_name": address_info["street_name"],
                "street_name_sv": address_info["street_name_sv"],
                "street_number": address_info["street_number"],
                "city": address_info["city"],
                "city_sv": address_info["city_sv"],
                "postal_code": address_info["postal_code"],
                "location": location,
                "zone": zone,
                "primary": True,
            },
        )[0]
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
        parking_permit = ParkingPermit.objects.create(
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
        comment = get_reversion_comment(EventType.CREATED, parking_permit)
        reversion.set_comment(comment)

    Order.objects.create_for_permits([parking_permit])
    return {"success": True, "permit": parking_permit}


@query.field("permitPriceChangeList")
@is_ad_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_permit_price_change_list(obj, info, permit_id, permit_info):
    try:
        permit = ParkingPermit.objects.get(identifier=permit_id)
    except ParkingPermit.DoesNotExist:
        raise ObjectNotFound(_("Parking permit not found"))

    customer_info = permit_info["customer"]
    if permit.customer.national_id_number != customer_info["national_id_number"]:
        raise UpdatePermitError(_("Cannot change the customer of the permit"))

    vehicle_info = permit_info["vehicle"]
    vehicle = update_or_create_vehicle(vehicle_info)
    parking_zone = ParkingZone.objects.get(name=customer_info["zone"])
    return permit.get_price_change_list(vehicle, parking_zone)


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
    permit = ParkingPermit.objects.get(identifier=permit_id)
    if permit.can_be_refunded:
        if not iban:
            raise RefundError("IBAN is not provided")
        description = f"Refund for ending permit #{permit.identifier}"
        Refund.objects.create(
            name=str(permit.customer),
            order=permit.order,
            amount=permit.get_refund_amount_for_unused_items(),
            iban=iban,
            description=description,
        )
    if permit.is_open_ended:
        # TODO: handle open ended. Currently how to handle
        # open ended permit are not defined.
        pass
    with reversion.create_revision():
        permit.end_permit(end_type)
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


@query.field("refunds")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_refunds(obj, info, page_input, order_by=None, search_items=None):
    refunds = Refund.objects.all().order_by("-created_at")
    if order_by:
        refunds = apply_ordering(refunds, order_by)
    if search_items:
        refunds = apply_filtering(refunds, search_items)
    paginator = QuerySetPaginator(refunds, page_input)
    return {
        "page_info": paginator.page_info,
        "objects": paginator.object_list,
    }


@query.field("refund")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_refund(obj, info, refund_number):
    try:
        return Refund.objects.get(refund_number=refund_number)
    except Refund.DoesNotExist:
        raise ObjectNotFound("Refund not found")


@mutation.field("updateRefund")
@is_ad_admin
@convert_kwargs_to_snake_case
def resolve_update_refund(obj, info, refund_number, refund):
    request = info.context["request"]
    try:
        r = Refund.objects.get(refund_number=refund_number)
    except Refund.DoesNotExist:
        raise ObjectNotFound("Refund not found")

    r.name = refund["name"]
    r.iban = refund["iban"]
    r.modified_by = request.user
    r.save()
    return {"success": True}
