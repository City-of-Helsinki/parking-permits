import logging
from collections import Counter
from copy import deepcopy

from ariadne import (
    MutationType,
    ObjectType,
    QueryType,
    ScalarType,
    UnionType,
    convert_kwargs_to_snake_case,
    snake_case_fallback_resolvers,
)
from dateutil.parser import isoparse
from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _

import audit_logger as audit
from audit_logger import AuditMsg
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
    TemporaryVehicle,
    Vehicle,
)
from parking_permits.models.vehicle import is_low_emission_vehicle
from users.models import ParkingPermitGroups

from .constants import EventFields, Origin
from .decorators import (
    is_customer_service,
    is_inspectors,
    is_preparators,
    is_sanctions,
    is_sanctions_and_refunds,
    is_super_admin,
)
from .exceptions import (
    AddressError,
    CreatePermitError,
    EndPermitError,
    ObjectNotFound,
    ParkingZoneError,
    ParkkihubiPermitError,
    PermitLimitExceeded,
    SearchError,
    TemporaryVehicleValidationError,
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
from .models.order import OrderPaymentType, OrderStatus, OrderType
from .models.parking_permit import (
    ContractType,
    ParkingPermitEvent,
    ParkingPermitEventFactory,
    ParkingPermitStatus,
)
from .models.refund import RefundStatus
from .models.vehicle import VehiclePowerType
from .services import kmo
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
from .utils import (
    ModelDiffer,
    get_end_time,
    get_permit_prices,
    get_user_from_resolver_args,
)

logger = logging.getLogger("db")
audit_logger = audit.getAuditLoggerAdapter(
    "audit",
    dict(
        origin=Origin.ADMIN_UI,
        reason=audit.Reason.ADMIN_SERVICE,
        event_type=audit.EventType.APP,
    ),
    autolog_config={
        "autoactor": get_user_from_resolver_args,
        "autostatus": True,
        "kwarg_name": "audit_msg",
    },
)

query = QueryType()
mutation = MutationType()
PermitDetail = ObjectType("PermitDetailNode")
parking_permit_event_gfk = UnionType("ParkingPermitEventGFK")
datetime_range_scalar = ScalarType("DateTimeRange")
schema_bindables = [
    query,
    mutation,
    PermitDetail,
    snake_case_fallback_resolvers,
    parking_permit_event_gfk,
    datetime_range_scalar,
]


def _audit_post_process_paged_search(
    msg,
    return_val,
    obj,
    info,
    page_input,
    *_,
    order_by=None,
    search_params=None,
    **__,
):
    """
    Custom-tailored audit log post-process hook for resolvers with the following signature:
    (obj, info, page_input, order_by=None, search_params=None) -> {"page_info": dict, "objects": QuerySet}
    """
    try:
        msg.extra = dict()
        msg.extra["page_info"] = page_input
        msg.extra["order_by"] = order_by
        msg.extra["search_params"] = search_params
        if return_val:
            msg.extra["page_info"] = return_val.get("page_info")
            msg.target = return_val.get("objects")
    except Exception as e:
        logger.error(
            "Something went wrong during audit message post processing", exc_info=e
        )


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


@datetime_range_scalar.serializer
def serialize_datetime_range(value):
    return value.lower, value.upper


@parking_permit_event_gfk.type_resolver
def resolve_gfk_type(obj, *_):
    if isinstance(obj, Order):
        return "OrderNode"
    if isinstance(obj, Refund):
        return "RefundNode"
    if isinstance(obj, TemporaryVehicle):
        return "TemporaryVehicleNode"
    return None


@query.field("permits")
@is_preparators
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "Admin searched for permits.",
        operation=audit.Operation.READ,
    ),
    post_process=_audit_post_process_paged_search,
)
def resolve_permits(obj, info, page_input, order_by=None, search_params=None):
    return get_permits(page_input, order_by, search_params)


@query.field("limitedPermits")
@is_inspectors
@convert_kwargs_to_snake_case
def resolve_limited_permits(obj, info, page_input, order_by=None, search_params=None):
    # add user role to search params
    search_params.update({"user_role": ParkingPermitGroups.INSPECTORS})
    return get_permits(page_input, order_by, search_params)


@query.field("permitDetail")
@is_preparators
@convert_kwargs_to_snake_case
def resolve_permit_detail(obj, info, permit_id):
    return ParkingPermit.objects.get(id=permit_id)


@PermitDetail.field("changeLogs")
def resolve_permit_detail_history(permit, info):
    events = ParkingPermitEvent.objects.filter(parking_permit=permit).order_by(
        "-created_at"
    )[:10]
    return events


@query.field("zones")
@is_customer_service
@convert_kwargs_to_snake_case
def resolve_zones(obj, info):
    return ParkingZone.objects.all().order_by("name")


@query.field("zoneByLocation")
@is_customer_service
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
@is_customer_service
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "Admin retrieved customer details.",
        operation=audit.Operation.READ,
    ),
    autotarget=audit.TARGET_RETURN,
    add_kwarg=True,
)
def resolve_customer(obj, info, audit_msg: AuditMsg = None, **data):
    query_params = data.get("query")
    customer = None

    try:
        customer = Customer.objects.get(**query_params)
    except Customer.DoesNotExist:
        if query_params.get("national_id_number"):
            # We're searching data from DVV now, so change the event type.
            audit_msg.event_type = audit.EventType.DVV
            logger.info("Customer does not exist, searching from DVV...")
            customer = get_person_info(query_params.get("national_id_number"))

        if not customer:
            raise ObjectNotFound(_("Person not found"))

    return customer


@query.field("customers")
@is_customer_service
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
@is_customer_service
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "Admin retrieved vehicle.",
        operation=audit.Operation.READ,
        event_type=audit.EventType.TRAFICOM,
    ),
    autotarget=audit.TARGET_RETURN,
)
def resolve_vehicle(obj, info, reg_number, national_id_number):
    vehicle = Traficom().fetch_vehicle_details(reg_number)
    if not settings.TRAFICOM_CHECK:
        return vehicle
    users_nin = [user._national_id_number for user in vehicle.users.all()]
    if vehicle and national_id_number in users_nin:
        return vehicle
    else:
        raise ObjectNotFound(_("Vehicle not found for the customer"))


def update_or_create_address(address_info):
    if not address_info:
        return None
    location = Point(*address_info["location"], srid=settings.SRID)
    address_obj = Address.objects.update_or_create(
        street_name=address_info["street_name"],
        street_number=address_info["street_number"],
        city=address_info["city"].title() if address_info["city"] else "",
        postal_code=address_info["postal_code"],
        location=location,
    )
    return address_obj[0]


def update_or_create_customer(customer_info):
    if customer_info["address_security_ban"]:
        customer_info.pop("first_name", None)
        customer_info.pop("last_name", None)
        customer_info.pop("primary_address", None)
        customer_info.pop("other_address", None)

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
    other_address = customer_info.get("other_address")

    if not customer_info["address_security_ban"] and (
        not primary_address and not other_address
    ):
        raise AddressError(
            _("Customer without address security ban must have one address selected")
        )

    if primary_address:
        customer_data["primary_address"] = update_or_create_address(primary_address)

    if other_address:
        customer_data["other_address"] = update_or_create_address(other_address)

    return Customer.objects.update_or_create(
        national_id_number=customer_info["national_id_number"], defaults=customer_data
    )[0]


def update_or_create_vehicle(vehicle_info):
    try:
        power_type = VehiclePowerType.objects.get(
            identifier=vehicle_info["power_type"]["identifier"]
        )
    except VehiclePowerType.DoesNotExist:
        raise ObjectNotFound(_("Vehicle power type not found"))

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
        "power_type": power_type,
    }
    return Vehicle.objects.update_or_create(
        registration_number=vehicle_info["registration_number"], defaults=vehicle_data
    )[0]


def update_or_create_customer_address(customer_info, permit_address):
    primary_address = None
    other_address = None
    primary_address_info = customer_info.get("primary_address")
    if primary_address_info:
        primary_address = update_or_create_address(primary_address_info)

    other_address_info = customer_info.get("other_address")
    if other_address_info:
        other_address = update_or_create_address(other_address_info)

    if (
        primary_address
        and permit_address
        and primary_address.zone == permit_address.zone
    ):
        return primary_address
    elif other_address and permit_address and other_address.zone == permit_address.zone:
        return other_address
    else:
        raise AddressError(_("Permit address does not have a valid zone"))


@query.field("addressSearch")
@convert_kwargs_to_snake_case
def resolve_address_search(obj, info, search_input):
    return kmo.search_address(search_text=search_input)


@mutation.field("createResidentPermit")
@is_customer_service
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "Admin created resident permit.",
        operation=audit.Operation.CREATE,
    ),
    add_kwarg=True,
)
@transaction.atomic
def resolve_create_resident_permit(obj, info, permit, audit_msg: AuditMsg = None):
    customer_info = permit["customer"]
    security_ban = customer_info.get("address_security_ban", False)
    national_id_number = customer_info["national_id_number"]
    if not national_id_number:
        raise CreatePermitError(
            _("Customer national id number is mandatory for the permit")
        )

    customer = update_or_create_customer(customer_info)
    active_permits = customer.active_permits
    active_permits_count = active_permits.count()
    if active_permits_count >= 2:
        raise PermitLimitExceeded(_("Cannot create more than 2 permits"))

    if active_permits_count == 1 and active_permits.first().is_open_ended:
        raise CreatePermitError(
            _(
                "Creating a fixed-period permit is not allowed when the first permit is open-ended"
            )
        )

    vehicle_info = permit["vehicle"]
    registration_number = vehicle_info["registration_number"]
    if not registration_number:
        raise CreatePermitError(
            _("Vehicle registration number is mandatory for the permit")
        )

    has_valid_permit = active_permits.filter(
        vehicle__registration_number=registration_number
    ).exists()
    if has_valid_permit:
        raise CreatePermitError(
            _("User already has a valid permit for the given vehicle.")
        )

    start_time = isoparse(permit["start_time"])
    month_count = permit["month_count"]
    end_time = get_end_time(start_time, month_count)
    if active_permits_count > 0:
        active_permit = active_permits[0]
        active_permit_end_time = active_permit.end_time
        if end_time > active_permit_end_time:
            end_time = active_permit_end_time
            month_count = active_permit.month_count

    vehicle = update_or_create_vehicle(vehicle_info)

    parking_zone = ParkingZone.objects.get(name=permit["zone"])
    permit_address = update_or_create_address(permit.get("address", None))
    if not security_ban:
        update_or_create_customer_address(customer_info, permit_address=permit_address)

    if active_permits_count == 1:
        active_parking_zone = active_permits[0].parking_zone
        if parking_zone != active_parking_zone:
            raise CreatePermitError(
                _(
                    "Cannot create permit. User already has a valid existing permit in zone %(parking_zone)s."
                )
                % {"parking_zone": active_parking_zone.name}
            )

    primary_vehicle = active_permits_count == 0
    parking_permit = ParkingPermit.objects.create(
        contract_type=ContractType.FIXED_PERIOD,
        customer=customer,
        vehicle=vehicle,
        parking_zone=parking_zone,
        status=permit["status"],
        start_time=start_time,
        month_count=month_count,
        end_time=end_time,
        description=permit["description"],
        address=permit_address if not security_ban else None,
        primary_vehicle=primary_vehicle,
    )

    audit_msg.target = parking_permit
    request = info.context["request"]
    ParkingPermitEventFactory.make_create_permit_event(
        parking_permit, created_by=request.user
    )

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
@is_customer_service
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_permit_prices(obj, info, permit, is_secondary):
    parking_zone = ParkingZone.objects.get(name=permit["zone"])
    vehicle_info = permit["vehicle"]

    power_type = VehiclePowerType.objects.get_or_create(**vehicle_info["power_type"])[0]
    euro_class = vehicle_info["euro_class"]
    emission_type = vehicle_info["emission_type"]
    emission = vehicle_info["emission"]

    is_low_emission = is_low_emission_vehicle(
        power_type, euro_class, emission_type, emission
    )

    start_time = isoparse(permit["start_time"])
    permit_start_date = start_time.date()
    end_time = get_end_time(start_time, permit["month_count"])
    permit_end_date = end_time.date()
    if is_secondary:
        active_permits = Customer.objects.get(
            national_id_number=permit.get("customer").get("national_id_number")
        ).active_permits
        active_permits_count = active_permits.count()
        if active_permits_count > 0:
            active_permit_end_time = active_permits[0].end_time
            if end_time > active_permit_end_time:
                permit_end_date = active_permit_end_time.date()

    return get_permit_prices(
        parking_zone,
        is_low_emission,
        is_secondary,
        permit_start_date,
        permit_end_date,
    )


@query.field("permitPriceChangeList")
@is_customer_service
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_permit_price_change_list(obj, info, permit_id, permit_info):
    try:
        permit = ParkingPermit.objects.get(id=permit_id)
    except ParkingPermit.DoesNotExist:
        raise ObjectNotFound(_("Parking permit not found"))

    address_changed = False
    previous_address_identifier = None
    if permit.address:
        previous_address_identifier = "%s %s" % (
            permit.address.street_name,
            permit.address.street_number,
        )
    customer_info = permit_info.get("customer")
    primary_address_info = customer_info.get("primary_address")
    if primary_address_info:
        address_identifier = "%s %s" % (
            primary_address_info.get("street_name"),
            primary_address_info.get("street_number"),
        )
        if address_identifier != previous_address_identifier:
            address_changed = True
    other_address_info = customer_info.get("other_address")
    if other_address_info:
        address_identifier = "%s %s" % (
            other_address_info.get("street_name"),
            other_address_info.get("street_number"),
        )
        if address_identifier != previous_address_identifier:
            address_changed = True

    price_change_list = []
    active_permits = permit.customer.active_permits
    fixed_period_permits = active_permits.fixed_period()
    if address_changed and fixed_period_permits.count() > 0:
        for permit in fixed_period_permits:
            update_price_change_list_for_permit(permit, permit_info, price_change_list)
    elif permit.is_fixed_period:
        update_price_change_list_for_permit(permit, permit_info, price_change_list)
    return price_change_list


def update_price_change_list_for_permit(permit, permit_info, price_change_list):
    customer_info = permit_info["customer"]
    if permit.customer.national_id_number != customer_info["national_id_number"]:
        raise UpdatePermitError(_("Cannot change the customer of the permit"))
    vehicle_info = permit_info["vehicle"]
    vehicle = Vehicle.objects.get(
        registration_number=vehicle_info["registration_number"]
    )
    is_low_emission = vehicle.is_low_emission
    parking_zone = ParkingZone.objects.get(name=permit_info["zone"])
    price_change_list.extend(
        permit.get_price_change_list(parking_zone, is_low_emission)
    )
    return price_change_list


@mutation.field("updateResidentPermit")
@is_customer_service
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "Admin updated resident permit.",
        operation=audit.Operation.UPDATE,
    ),
    add_kwarg=True,
)
@transaction.atomic
def resolve_update_resident_permit(
    obj, info, permit_id, permit_info, iban=None, audit_msg: AuditMsg = None
):
    try:
        permit = ParkingPermit.objects.get(id=permit_id)
    except ParkingPermit.DoesNotExist:
        raise ObjectNotFound(_("Parking permit not found"))

    request = info.context["request"]
    audit_msg.target = permit
    customer_info = permit_info["customer"]
    security_ban = customer_info.get("address_security_ban", False)

    national_id_number = customer_info["national_id_number"]
    if not national_id_number:
        raise UpdatePermitError(
            _("Customer national id number is mandatory for the permit")
        )
    if permit.customer.national_id_number != national_id_number:
        raise UpdatePermitError(_("Cannot change the customer of the permit"))

    vehicle_info = permit_info["vehicle"]
    registration_number = vehicle_info["registration_number"]
    if not registration_number:
        raise UpdatePermitError(
            _("Vehicle registration number is mandatory for the permit")
        )

    active_permits = permit.customer.active_permits
    has_valid_permit = (
        active_permits.filter(vehicle__registration_number=registration_number)
        .exclude(id=permit_id)
        .exists()
    )
    if has_valid_permit:
        raise UpdatePermitError(
            _("User already has a valid other permit for the given vehicle.")
        )

    vehicle_changed = False
    previous_vehicle_registration_number = permit.vehicle.registration_number
    if registration_number != previous_vehicle_registration_number:
        previous_permit = deepcopy(permit)
        vehicle_changed = True

    address_changed = False
    previous_address_id = permit.address.id if permit.address else None
    new_zone = ParkingZone.objects.get(name=permit_info.get("zone"))
    permit_address = update_or_create_address(permit_info.get("address", None))
    if not security_ban:
        update_or_create_customer_address(customer_info, permit_address=permit_address)
    if (previous_address_id and not permit_address) or (
        permit_address and permit_address.id != previous_address_id
    ):
        address_changed = True

    if address_changed and active_permits.count() == 2:
        first_permit = active_permits[0]
        second_permit = active_permits[1]
        if first_permit.contract_type != second_permit.contract_type:
            raise UpdatePermitError(
                _(
                    "Changing address for different type (fixed-period / open-ended) permits is not allowed"
                )
            )

    total_price_change_by_order = Counter()
    fixed_period_permits = active_permits.fixed_period()
    if address_changed and fixed_period_permits.count() > 0:
        for permit in fixed_period_permits:
            calculate_total_price_change(
                new_zone, permit, permit_info, total_price_change_by_order
            )
    elif vehicle_changed:
        calculate_total_price_change(
            new_zone, permit, permit_info, total_price_change_by_order
        )

    # total price changes for customer's all valid permits
    customer_total_price_change = sum(total_price_change_by_order.values())

    customer = update_or_create_customer(customer_info)

    for order, order_total_price_change in total_price_change_by_order.items():
        if customer_total_price_change < 0:
            logger.info("Creating refund for current order")
            refund = Refund.objects.create(
                name=str(customer),
                order=order,
                amount=-customer_total_price_change,
                iban=iban,
                description=f"Refund for updating permit: {permit.id}",
            )
            logger.info(f"Refund for lowered permit price created: {refund}")
            ParkingPermitEventFactory.make_create_refund_event(
                permit, refund, created_by=request.user
            )
            send_refund_email(RefundEmailType.CREATED, customer, refund)

    # Update permit address and zone for all active permits
    for permit in active_permits:
        permit.parking_zone = new_zone
        permit.address = permit_address if not security_ban else None
        permit.save()

    # get updated permit info
    permit = ParkingPermit.objects.get(id=permit_id)

    customer_diff = ModelDiffer.get_diff(
        permit.customer,
        customer,
        fields=EventFields.CUSTOMER,
    )
    vehicle = update_or_create_vehicle(vehicle_info)
    vehicle_diff = ModelDiffer.get_diff(
        permit.vehicle,
        vehicle,
        fields=EventFields.VEHICLE,
    )
    with ModelDiffer(permit, fields=EventFields.PERMIT) as permit_diff:
        permit.status = permit_info["status"]
        permit.vehicle = vehicle
        permit.description = permit_info["description"]
        permit.save()

    ParkingPermitEventFactory.make_update_permit_event(
        permit,
        created_by=request.user,
        changes={**permit_diff, "customer": customer_diff, "vehicle": vehicle_diff},
    )
    # get updated permit info
    permit = ParkingPermit.objects.get(id=permit_id)
    permit.update_parkkihubi_permit()

    if address_changed:
        for active_permit in active_permits.all():
            send_permit_email(PermitEmailType.UPDATED, active_permit)
    else:
        send_permit_email(PermitEmailType.UPDATED, permit)

    if vehicle_changed:
        if previous_permit.vehicle.is_low_emission:
            send_vehicle_low_emission_discount_email(
                PermitEmailType.VEHICLE_LOW_EMISSION_DISCOUNT_DEACTIVATED,
                previous_permit,
            )
        if permit.consent_low_emission_accepted and permit.vehicle.is_low_emission:
            send_vehicle_low_emission_discount_email(
                PermitEmailType.VEHICLE_LOW_EMISSION_DISCOUNT_ACTIVATED, permit
            )
    if permit.is_fixed_period:
        logger.info(f"Creating renewal order for permit: {permit.id}")
        new_order = Order.objects.create_renewal_order(
            customer,
            status=OrderStatus.CONFIRMED,
            payment_type=OrderPaymentType.CASHIER_PAYMENT,
        )
        logger.info(f"Creating renewal order completed: {new_order.id}")
    return {"success": True}


def calculate_total_price_change(
    new_zone, permit, permit_info, total_price_change_by_order
):
    vehicle_info = permit_info["vehicle"]
    vehicle = Vehicle.objects.get(
        registration_number=vehicle_info["registration_number"]
    )
    is_low_emission = vehicle.is_low_emission
    price_change_list = permit.get_price_change_list(new_zone, is_low_emission)
    permit_total_price_change = sum(
        [item["price_change"] * item["month_count"] for item in price_change_list]
    )
    total_price_change_by_order.update({permit.latest_order: permit_total_price_change})


@mutation.field("endPermit")
@is_customer_service
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "Admin ended resident permit.",
        operation=audit.Operation.UPDATE,
    ),
    add_kwarg=True,
)
@transaction.atomic
def resolve_end_permit(
    obj, info, permit_id, end_type, iban=None, audit_msg: AuditMsg = None
):
    request = info.context["request"]
    permit = ParkingPermit.objects.get(id=permit_id)
    audit_msg.target = permit

    if permit.customer.active_permits.count() > 1 and permit.primary_vehicle:
        raise EndPermitError(
            _("Primary permit cannot be ended if customer has two permits")
        )

    if permit.can_be_refunded:
        total_sum = permit.total_refund_amount
        refund = Refund.objects.filter(order=permit.latest_order)
        if refund.exists():
            order = Order.objects.create_renewal_order(
                permit.customer,
                status=OrderStatus.CONFIRMED,
                order_type=OrderType.CREATED,
                payment_type=OrderPaymentType.CASHIER_PAYMENT,
                user=request.user,
            )
            total_sum = order.total_price
            order.order_items.all().delete()
        else:
            order = permit.latest_order
        if total_sum > 0:
            description = f"Refund for ending permit #{permit.id}"
            refund = Refund.objects.create(
                name=str(permit.customer),
                order=order,
                amount=total_sum,
                iban=iban,
                description=description,
            )
            send_refund_email(RefundEmailType.CREATED, permit.customer, refund)
            ParkingPermitEventFactory.make_create_refund_event(
                permit, refund, created_by=request.user
            )

    permit.end_permit(end_type)

    ParkingPermitEventFactory.make_end_permit_event(permit, created_by=request.user)

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
    _product.create_talpa_product()
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
    product = Product.objects.create(
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
    product.create_talpa_product()
    return {"success": True}


@query.field("refunds")
@is_preparators
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "Admin searched for refunds.",
        operation=audit.Operation.READ,
    ),
    post_process=_audit_post_process_paged_search,
)
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
        accepted_at=tz.now(),
        accepted_by=request.user,
    )
    accepted_refunds = Refund.objects.filter(
        id__in=ids, status=RefundStatus.ACCEPTED
    ).select_related("order__customer")
    for refund in accepted_refunds:
        send_refund_email(RefundEmailType.ACCEPTED, refund.order.customer, refund)
    return qs.count()


@query.field("refund")
@is_customer_service
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
@audit_logger.autolog(
    AuditMsg(
        "Admin searched for orders.",
        operation=audit.Operation.READ,
    ),
    post_process=_audit_post_process_paged_search,
)
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


@mutation.field("addTemporaryVehicle")
@is_customer_service
@convert_kwargs_to_snake_case
@transaction.atomic
def add_temporary_vehicle(
    obj, info, permit_id, registration_number, start_time, end_time
):
    request = info.context["request"]
    has_valid_permit = ParkingPermit.objects.filter(
        vehicle__registration_number=registration_number,
        status__in=[ParkingPermitStatus.VALID, ParkingPermitStatus.PAYMENT_IN_PROGRESS],
    ).exists()

    if has_valid_permit:
        raise TemporaryVehicleValidationError(
            _("There's already a valid permit for a given vehicle.")
        )

    permit = ParkingPermit.objects.get(id=permit_id)

    if tz.localtime(isoparse(start_time)) < tz.now():
        raise TemporaryVehicleValidationError(_("Start time cannot be in the past"))

    if tz.localtime(isoparse(start_time)) < permit.start_time:
        raise TemporaryVehicleValidationError(
            _("Temporary vehicle start time has to be after permit start time")
        )

    tmp_vehicle = Traficom().fetch_vehicle_details(
        registration_number=registration_number
    )
    vehicle = TemporaryVehicle.objects.create(
        vehicle=tmp_vehicle,
        end_time=end_time,
        start_time=start_time,
    )
    permit.temp_vehicles.add(vehicle)
    ParkingPermitEventFactory.make_add_temporary_vehicle_event(
        permit, vehicle, request.user
    )
    permit.update_parkkihubi_permit()
    send_permit_email(PermitEmailType.TEMP_VEHICLE_ACTIVATED, permit)
    return {"success": True}


@mutation.field("removeTemporaryVehicle")
@is_customer_service
@convert_kwargs_to_snake_case
@transaction.atomic
def remove_temporary_vehicle(obj, info, permit_id):
    request = info.context["request"]
    permit = ParkingPermit.objects.get(id=permit_id)
    active_temp_vehicles = permit.temp_vehicles.filter(is_active=True)
    prev_active_temp_vehicles = list(active_temp_vehicles)

    active_temp_vehicles.update(is_active=False)
    permit.update_parkkihubi_permit()

    for temp_vehicle in prev_active_temp_vehicles:
        ParkingPermitEventFactory.make_remove_temporary_vehicle_event(
            permit, temp_vehicle, request.user
        )

    send_permit_email(PermitEmailType.TEMP_VEHICLE_DEACTIVATED, permit)

    return {"success": True}
