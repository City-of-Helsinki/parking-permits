import logging
from copy import deepcopy

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
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from parking_permits.models import (
    Address,
    Announcement,
    Customer,
    LowEmissionCriteria,
    Order,
    ParkingPermit,
    ParkingZone,
    Product,
    Refund,
    Vehicle,
)

from .decorators import (
    is_customer_service,
    is_inspectors,
    is_preparators,
    is_sanctions,
    is_sanctions_and_refunds,
    is_super_admin,
)
from .exceptions import (
    CreatePermitError,
    ObjectNotFound,
    ParkingZoneError,
    ParkkihubiPermitError,
    PermitLimitExceeded,
    RefundError,
    SearchError,
    UpdatePermitError,
)
from .forms import (
    AddressSearchForm,
    AnnouncementSearchForm,
    CustomerSearchForm,
    LowEmissionCriteriaSearchForm,
    OrderSearchForm,
    PermitSearchForm,
    ProductSearchForm,
    RefundSearchForm,
)
from .models.order import OrderStatus
from .models.parking_permit import ContractType
from .models.refund import RefundStatus
from .reversion import EventType, get_obj_changelogs, get_reversion_comment
from .services.dvv import get_person_info
from .services.mail import (
    PermitEmailType,
    RefundEmailType,
    send_announcement_email,
    send_permit_email,
    send_refund_email,
    send_vehicle_low_emission_discount_email,
)
from .services.traficom import Traficom
from .utils import get_end_time, get_permit_prices

logger = logging.getLogger("db")

query = QueryType()
mutation = MutationType()
PermitDetail = ObjectType("PermitDetailNode")
schema_bindables = [query, mutation, PermitDetail, snake_case_fallback_resolvers]


def get_permits(page_input, order_by=None, search_params=None):
    form_data = {**page_input}
    if order_by:
        form_data.update(order_by)
    if search_params:
        form_data.update(search_params)

    form = PermitSearchForm(form_data)
    if not form.is_valid():
        logger.error(f"Permit Search Error: {form.errors}")
        raise SearchError(_("Permit search error"))
    return form.get_paged_queryset()


@query.field("permits")
@is_preparators
@convert_kwargs_to_snake_case
def resolve_permits(obj, info, page_input, order_by=None, search_params=None):
    return get_permits(page_input, order_by, search_params)


@query.field("limitedPermits")
@is_inspectors
@convert_kwargs_to_snake_case
def resolve_limited_permits(obj, info, page_input, order_by=None, search_params=None):
    return get_permits(page_input, order_by, search_params)


@query.field("permitDetail")
@is_preparators
@convert_kwargs_to_snake_case
def resolve_permit_detail(obj, info, permit_id):
    return ParkingPermit.objects.get(id=permit_id)


@PermitDetail.field("changeLogs")
def resolve_permit_detail_history(permit, info):
    return get_obj_changelogs(permit)


@query.field("zones")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_zones(obj, info):
    return ParkingZone.objects.all().order_by("name")


@query.field("zoneByLocation")
@is_super_admin
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
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_customer(obj, info, **data):
    query_params = data.get("query")
    try:
        customer = Customer.objects.get(**query_params)
    except Customer.DoesNotExist:
        customer = None
        if query_params.get("national_id_number"):
            logger.info("Customer does not exist, searching from DVV...")
            customer = get_person_info(query_params.get("national_id_number"))
        if not customer:
            raise ObjectNotFound(_("Person not found"))
    return customer


@query.field("customers")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_customers(obj, info, page_input, order_by=None, search_params=None):
    form_data = {**page_input}
    if order_by:
        form_data.update(order_by)
    if search_params:
        form_data.update(search_params)

    form = CustomerSearchForm(form_data)
    if not form.is_valid():
        logger.error(f"Customer search error: {form.errors}")
        raise SearchError(_("Customer search error"))
    return form.get_paged_queryset()


@query.field("vehicle")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_vehicle(obj, info, reg_number, national_id_number):
    vehicle = Traficom().fetch_vehicle_details(reg_number)
    if not settings.TRAFICOM_CHECK:
        return vehicle
    users_nin = [user._national_id_number for user in vehicle.users.all()]
    if vehicle and national_id_number in users_nin:
        return vehicle
    else:
        raise ObjectNotFound(_("Vehicle not found for the customer"))


def create_address(address_info):
    address_obj = Address.objects.update_or_create(
        street_name=address_info["street_name"],
        street_number=address_info["street_number"],
        city=address_info["city"],
        postal_code=address_info["postal_code"],
        defaults=address_info,
    )
    return address_obj[0]


def update_or_create_customer(customer_info):
    if customer_info["address_security_ban"]:
        customer_info.pop("first_name", None)
        customer_info.pop("last_name", None)
        customer_info.pop("primary_address", None)

    customer_data = {
        "first_name": customer_info.get("first_name", ""),
        "last_name": customer_info.get("last_name", ""),
        "national_id_number": customer_info["national_id_number"],
        "email": customer_info["email"],
        "phone_number": customer_info["phone_number"],
        "address_security_ban": customer_info["address_security_ban"],
        "driver_license_checked": customer_info["driver_license_checked"],
    }

    primary_address = customer_info.get("primary_address")
    if primary_address:
        customer_data["primary_address"] = create_address(primary_address)

    other_address = customer_info.get("other_address")
    if other_address:
        customer_data["other_address"] = create_address(other_address)

    return Customer.objects.update_or_create(
        national_id_number=customer_info["national_id_number"], defaults=customer_data
    )[0]


def update_or_create_vehicle(vehicle_info):
    vehicle_data = {
        "registration_number": vehicle_info["registration_number"],
        "manufacturer": vehicle_info["manufacturer"],
        "model": vehicle_info["model"],
        "consent_low_emission_accepted": vehicle_info["consent_low_emission_accepted"],
        "serial_number": vehicle_info["serial_number"],
        "vehicle_class": vehicle_info["vehicle_class"],
        "euro_class": vehicle_info["euro_class"],
        "emission": vehicle_info["emission"],
        "emission_type": vehicle_info["emission_type"],
        "power_type": vehicle_info["power_type"],
    }
    return Vehicle.objects.update_or_create(
        registration_number=vehicle_info["registration_number"], defaults=vehicle_data
    )[0]


def create_permit_address(customer_info):
    primary_address = customer_info.get("primary_address")
    if primary_address:
        return create_address(primary_address)

    other_address = customer_info.get("other_address")
    if other_address:
        return create_address(other_address)


@mutation.field("createResidentPermit")
@is_customer_service
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_create_resident_permit(obj, info, permit):
    customer_info = permit["customer"]
    customer = update_or_create_customer(customer_info)
    active_permits = customer.active_permits
    active_permits_count = active_permits.count()
    if active_permits_count >= 2:
        raise PermitLimitExceeded(_("Cannot create more than 2 permits"))

    start_time = isoparse(permit["start_time"])
    end_time = get_end_time(start_time, permit["month_count"])
    if active_permits_count == 1 and end_time > active_permits[0].end_time:
        raise CreatePermitError(
            _("The validity period of secondary permit cannot exceeds the primary one")
        )

    vehicle_info = permit["vehicle"]
    vehicle = update_or_create_vehicle(vehicle_info)

    address = create_permit_address(customer_info)

    parking_zone = ParkingZone.objects.get(name=customer_info["zone"])
    primary_vehicle = active_permits_count == 0
    with reversion.create_revision():
        parking_permit = ParkingPermit.objects.create(
            contract_type=ContractType.FIXED_PERIOD,
            customer=customer,
            vehicle=vehicle,
            parking_zone=parking_zone,
            status=permit["status"],
            start_time=start_time,
            month_count=permit["month_count"],
            end_time=end_time,
            description=permit["description"],
            address=address,
            primary_vehicle=primary_vehicle,
        )
        request = info.context["request"]
        reversion.set_user(request.user)
        comment = get_reversion_comment(EventType.CREATED, parking_permit)
        reversion.set_comment(comment)

    # when creating from Admin UI, it's considered the payment is completed
    # and the order status should be confirmed
    Order.objects.create_for_permits([parking_permit], status=OrderStatus.CONFIRMED)
    try:
        parking_permit.update_parkkihubi_permit()
    except ParkkihubiPermitError:
        parking_permit.create_parkkihubi_permit()
    send_permit_email(PermitEmailType.CREATED, parking_permit)
    if (
        parking_permit.consent_low_emission_accepted
        and parking_permit.vehicle.is_low_emission
    ):
        send_vehicle_low_emission_discount_email(
            PermitEmailType.VEHICLE_LOW_EMISSION_DISCOUNT_ACTIVATED, parking_permit
        )
    return {"success": True, "permit": parking_permit}


@query.field("permitPrices")
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_permit_prices(obj, info, permit, is_secondary):
    parking_zone = ParkingZone.objects.get(name=permit["customer"]["zone"])
    vehicle_info = permit["vehicle"]
    vehicle = Vehicle.objects.get(
        registration_number=vehicle_info["registration_number"]
    )
    is_low_emission = vehicle.is_low_emission
    start_time = isoparse(permit["start_time"])
    permit_start_date = start_time.date()
    end_time = get_end_time(start_time, permit["month_count"])
    permit_end_date = end_time.date()
    return get_permit_prices(
        parking_zone,
        is_low_emission,
        is_secondary,
        permit_start_date,
        permit_end_date,
    )


@query.field("permitPriceChangeList")
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_permit_price_change_list(obj, info, permit_id, permit_info):
    try:
        permit = ParkingPermit.objects.get(id=permit_id)
    except ParkingPermit.DoesNotExist:
        raise ObjectNotFound(_("Parking permit not found"))

    customer_info = permit_info["customer"]
    if permit.customer.national_id_number != customer_info["national_id_number"]:
        raise UpdatePermitError(_("Cannot change the customer of the permit"))

    vehicle_info = permit_info["vehicle"]
    vehicle = Vehicle.objects.get(
        registration_number=vehicle_info["registration_number"]
    )
    is_low_emission = vehicle.is_low_emission
    parking_zone = ParkingZone.objects.get(name=customer_info["zone"])
    return permit.get_price_change_list(parking_zone, is_low_emission)


@mutation.field("updateResidentPermit")
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_update_resident_permit(obj, info, permit_id, permit_info, iban=None):
    try:
        permit = ParkingPermit.objects.get(id=permit_id)
    except ParkingPermit.DoesNotExist:
        raise ObjectNotFound(_("Parking permit not found"))

    customer_info = permit_info["customer"]
    if permit.customer.national_id_number != customer_info["national_id_number"]:
        raise UpdatePermitError(_("Cannot change the customer of the permit"))
    vehicle_info = permit_info["vehicle"]

    vehicle_changed = False
    previous_vehicle_registration_number = permit.vehicle.registration_number
    new_vehicle_registration_number = vehicle_info["registration_number"]
    if new_vehicle_registration_number != previous_vehicle_registration_number:
        previous_permit = deepcopy(permit)
        vehicle_changed = True

    new_vehicle = Vehicle.objects.get(
        registration_number=new_vehicle_registration_number
    )
    is_low_emission = new_vehicle.is_low_emission

    parking_zone = ParkingZone.objects.get(name=customer_info["zone"])

    price_change_list = permit.get_price_change_list(parking_zone, is_low_emission)
    total_price_change = sum([item["price_change"] for item in price_change_list])

    # only create new order when emission status or parking zone changed
    should_create_new_order = (
        permit.vehicle.is_low_emission != is_low_emission
        or permit.parking_zone_id != parking_zone.id
    )

    customer = update_or_create_customer(customer_info)
    vehicle = update_or_create_vehicle(vehicle_info)
    with reversion.create_revision():
        permit.status = permit_info["status"]
        permit.parking_zone = parking_zone
        permit.vehicle = vehicle
        permit.description = permit_info["description"]
        permit.save()
        request = info.context["request"]
        reversion.set_user(request.user)
        comment = get_reversion_comment(EventType.CHANGED, permit)
        reversion.set_comment(comment)

    if should_create_new_order:
        if total_price_change > 0:
            logger.info("Creating refund for current order")
            refund = Refund.objects.create(
                name=str(customer),
                order=permit.latest_order,
                amount=total_price_change,
                iban=iban,
                description=f"Refund for updating permit: {permit.id}",
            )
            logger.info(f"Refund for lowered permit price created: {refund}")
            send_refund_email(RefundEmailType.CREATED, customer, refund)
        logger.info(f"Creating renewal order for permit: {permit.id}")
        new_order = Order.objects.create_renewal_order(
            customer, status=OrderStatus.CONFIRMED
        )
        logger.info(f"Creating renewal order completed: {new_order.id}")

    # get updated permit info
    permit = ParkingPermit.objects.get(id=permit_id)
    permit.update_parkkihubi_permit()
    send_permit_email(PermitEmailType.UPDATED, permit)
    if vehicle_changed:
        if previous_permit.vehicle.is_low_emission:
            previous_permit.end_time = permit.start_time
            send_vehicle_low_emission_discount_email(
                PermitEmailType.VEHICLE_LOW_EMISSION_DISCOUNT_DEACTIVATED,
                previous_permit,
            )
        if permit.consent_low_emission_accepted and permit.vehicle.is_low_emission:
            send_vehicle_low_emission_discount_email(
                PermitEmailType.VEHICLE_LOW_EMISSION_DISCOUNT_ACTIVATED, permit
            )
    return {"success": True}


@mutation.field("endPermit")
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_end_permit(obj, info, permit_id, end_type, iban=None):
    request = info.context["request"]
    permit = ParkingPermit.objects.get(id=permit_id)
    if permit.can_be_refunded:
        if not iban:
            raise RefundError(_("IBAN is not provided"))
        if permit.get_refund_amount_for_unused_items() > 0:
            description = f"Refund for ending permit #{permit.id}"
            refund = Refund.objects.create(
                name=str(permit.customer),
                order=permit.latest_order,
                amount=permit.get_refund_amount_for_unused_items(),
                iban=iban,
                description=description,
            )
            send_refund_email(RefundEmailType.CREATED, permit.customer, refund)
    if permit.is_open_ended:
        # TODO: handle open ended. Currently how to handle
        # open ended permit are not defined.
        pass
    with reversion.create_revision():
        permit.end_permit(end_type)
        reversion.set_user(request.user)
        comment = get_reversion_comment(EventType.CHANGED, permit)
        reversion.set_comment(comment)

    # get updated permit info
    permit = ParkingPermit.objects.get(id=permit_id)
    permit.update_parkkihubi_permit()
    send_permit_email(PermitEmailType.ENDED, permit)
    if permit.consent_low_emission_accepted and permit.vehicle.is_low_emission:
        send_vehicle_low_emission_discount_email(
            PermitEmailType.VEHICLE_LOW_EMISSION_DISCOUNT_DEACTIVATED, permit
        )
    return {"success": True}


@query.field("products")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_products(obj, info, page_input, order_by=None):
    form_data = {**page_input}
    if order_by:
        form_data.update(order_by)

    form = ProductSearchForm(form_data)
    if not form.is_valid():
        logger.error(f"Product Search Error: {form.errors}")
        raise SearchError(_("Product search error"))
    return form.get_paged_queryset()


@query.field("product")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_product(obj, info, product_id):
    return Product.objects.get(id=product_id)


@mutation.field("updateProduct")
@is_super_admin
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
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_delete_product(obj, info, product_id):
    product = Product.objects.get(id=product_id)
    product.delete()
    return {"success": True}


@mutation.field("createProduct")
@is_super_admin
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
@is_preparators
@convert_kwargs_to_snake_case
def resolve_refunds(obj, info, page_input, order_by=None, search_params=None):
    form_data = {**page_input}
    if order_by:
        form_data.update(order_by)
    if search_params:
        form_data.update(search_params)

    form = RefundSearchForm(form_data)
    if not form.is_valid():
        logger.error(f"Refund Search Error: {form.errors}")
        raise SearchError(_("Refund search error"))
    return form.get_paged_queryset()


@mutation.field("requestForApproval")
@is_sanctions
@convert_kwargs_to_snake_case
def resolve_request_for_approval(obj, info, ids):
    qs = Refund.objects.filter(id__in=ids, status=RefundStatus.OPEN)
    qs.update(status=RefundStatus.REQUEST_FOR_APPROVAL)
    return qs.count()


@mutation.field("acceptRefunds")
@is_sanctions_and_refunds
@convert_kwargs_to_snake_case
def resolve_accept_refunds(obj, info, ids):
    request = info.context["request"]
    qs = Refund.objects.filter(id__in=ids, status=RefundStatus.REQUEST_FOR_APPROVAL)
    qs.update(
        status=RefundStatus.ACCEPTED,
        accepted_at=timezone.now(),
        accepted_by=request.user,
    )
    accepted_refunds = Refund.objects.filter(
        id__in=ids, status=RefundStatus.ACCEPTED
    ).select_related("order__customer")
    for refund in accepted_refunds:
        send_refund_email(RefundEmailType.ACCEPTED, refund.order.customer, refund)
    return qs.count()


@query.field("refund")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_refund(obj, info, refund_id):
    try:
        return Refund.objects.get(id=refund_id)
    except Refund.DoesNotExist:
        raise ObjectNotFound(_("Refund not found"))


@mutation.field("updateRefund")
@is_customer_service
@convert_kwargs_to_snake_case
def resolve_update_refund(obj, info, refund_id, refund):
    request = info.context["request"]
    try:
        r = Refund.objects.get(id=refund_id)
    except Refund.DoesNotExist:
        raise ObjectNotFound(_("Refund not found"))

    r.name = refund["name"]
    r.iban = refund["iban"]
    r.modified_by = request.user
    r.save()
    return {"success": True}


@query.field("orders")
@is_preparators
@convert_kwargs_to_snake_case
def resolve_orders(obj, info, page_input, order_by=None, search_params=None):
    form_data = {**page_input}
    if order_by:
        form_data.update(order_by)
    if search_params:
        form_data.update(search_params)

    form = OrderSearchForm(form_data)
    if not form.is_valid():
        logger.error(f"Order Search Error: {form.errors}")
        raise SearchError(_("Order search error"))
    return form.get_paged_queryset()


@query.field("addresses")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_addresses(obj, info, page_input, order_by=None, search_params=None):
    form_data = {**page_input}
    if order_by:
        form_data.update(order_by)
    if search_params:
        form_data.update(search_params)

    form = AddressSearchForm(form_data)
    if not form.is_valid():
        logger.error(f"Address Search Error: {form.errors}")
        raise SearchError(_("Address search error"))
    return form.get_paged_queryset()


@query.field("address")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_address(obj, info, address_id):
    return Address.objects.get(id=address_id)


@mutation.field("updateAddress")
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_update_address(obj, info, address_id, address):
    location = Point(*address["location"], srid=settings.SRID)
    _address = Address.objects.get(id=address_id)
    _address.street_name = address["street_name"]
    _address.street_name_sv = address["street_name_sv"]
    _address.street_number = address["street_number"]
    _address.postal_code = address["postal_code"]
    _address.city = address["city"]
    _address.city_sv = address["city_sv"]
    _address.location = location
    _address.save()
    return {"success": True}


@mutation.field("deleteAddress")
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_delete_address(obj, info, address_id):
    address = Address.objects.get(id=address_id)
    address.delete()
    return {"success": True}


@mutation.field("createAddress")
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_create_address(obj, info, address):
    location = Point(*address["location"], srid=settings.SRID)
    Address.objects.create(
        street_name=address["street_name"],
        street_name_sv=address["street_name_sv"],
        street_number=address["street_number"],
        postal_code=address["postal_code"],
        city=address["city"],
        city_sv=address["city_sv"],
        location=location,
    )
    return {"success": True}


@query.field("lowEmissionCriteria")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_low_emission_criteria(obj, info, page_input, order_by=None):
    form_data = {**page_input}
    if order_by:
        form_data.update(order_by)

    form = LowEmissionCriteriaSearchForm(form_data)
    if not form.is_valid():
        logger.error(f"Low emission criteria Search Error: {form.errors}")
        raise SearchError("Low emission criteria search error")
    return form.get_paged_queryset()


@query.field("lowEmissionCriterion")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_low_emission_criterion(obj, info, criterion_id):
    return LowEmissionCriteria.objects.get(id=criterion_id)


@mutation.field("updateLowEmissionCriterion")
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_update_low_emission_criterion(obj, info, criterion_id, criterion):
    _criterion = LowEmissionCriteria.objects.get(id=criterion_id)
    _criterion.nedc_max_emission_limit = criterion["nedc_max_emission_limit"]
    _criterion.wltp_max_emission_limit = criterion["wltp_max_emission_limit"]
    _criterion.euro_min_class_limit = criterion["euro_min_class_limit"]
    _criterion.start_date = criterion["start_date"]
    _criterion.end_date = criterion["end_date"]
    _criterion.save()
    return {"success": True}


@mutation.field("deleteLowEmissionCriterion")
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_delete_low_emission_criterion(obj, info, criterion_id):
    criterion = LowEmissionCriteria.objects.get(id=criterion_id)
    criterion.delete()
    return {"success": True}


@mutation.field("createLowEmissionCriterion")
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_create_low_emission_criterion(obj, info, criterion):
    LowEmissionCriteria.objects.create(
        nedc_max_emission_limit=criterion["nedc_max_emission_limit"],
        wltp_max_emission_limit=criterion["wltp_max_emission_limit"],
        euro_min_class_limit=criterion["euro_min_class_limit"],
        start_date=criterion["start_date"],
        end_date=criterion["end_date"],
    )
    return {"success": True}


@query.field("announcements")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_announcements(obj, info, page_input, order_by=None):
    form_data = {**page_input}
    if order_by:
        form_data.update(order_by)

    form = AnnouncementSearchForm(form_data)
    if not form.is_valid():
        logger.error(f"Announcement search error: {form.errors}")
        raise SearchError(_("Announcement search error"))
    return form.get_paged_queryset()


@query.field("announcement")
@is_super_admin
@convert_kwargs_to_snake_case
def resolve_announcement(obj, info, announcement_id):
    try:
        return Announcement.objects.get(id=announcement_id)
    except Announcement.DoesNotExist:
        raise ObjectNotFound(_("Announcement not found"))


def post_create_announcement(announcement: Announcement):
    customers = Customer.objects.filter(zone__in=announcement.parking_zones)
    send_announcement_email(customers, announcement)


@mutation.field("createAnnouncement")
@is_super_admin
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_create_announcement(obj, info, announcement):
    request = info.context["request"]
    new_announcement = Announcement.objects.create(
        created_by=request.user,
        content_fi=announcement["content_fi"],
        content_en=announcement["content_en"],
        content_sv=announcement["content_sv"],
        subject_en=announcement["subject_en"],
        subject_fi=announcement["subject_fi"],
        subject_sv=announcement["subject_sv"],
    )
    if announcement.get("parking_zones"):
        new_announcement._parking_zones.set(
            ParkingZone.objects.filter(name__in=announcement["parking_zones"])
        )

    post_create_announcement(new_announcement)

    return {"success": True}
