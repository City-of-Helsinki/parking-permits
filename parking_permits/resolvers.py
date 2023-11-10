import logging
from collections import Counter

from ariadne import (
    MutationType,
    QueryType,
    convert_kwargs_to_snake_case,
    load_schema_from_path,
    snake_case_fallback_resolvers,
)
from ariadne.contrib.federation import FederatedObjectType
from dateutil.parser import isoparse
from django.db import transaction
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _

import audit_logger as audit
from audit_logger import AuditMsg
from project.settings import BASE_DIR

from .constants import EventFields, Origin
from .customer_permit import CustomerPermit
from .decorators import is_authenticated
from .exceptions import (
    AddressError,
    ObjectNotFound,
    ParkingZoneError,
    TemporaryVehicleValidationError,
    TraficomFetchVehicleError,
)
from .models import Address, Customer, Refund, Vehicle
from .models.order import Order, OrderPaymentType, OrderStatus, OrderType
from .models.parking_permit import (
    ContractType,
    ParkingPermit,
    ParkingPermitEventFactory,
    ParkingPermitStatus,
)
from .services.dvv import get_addresses
from .services.hel_profile import HelsinkiProfile
from .services.mail import (
    PermitEmailType,
    RefundEmailType,
    send_permit_email,
    send_refund_email,
)
from .services.traficom import Traficom
from .talpa.order import TalpaOrderManager
from .utils import ModelDiffer, get_user_from_resolver_args

logger = logging.getLogger("db")
audit_logger = audit.getAuditLoggerAdapter(
    "audit",
    dict(
        origin=Origin.WEBSHOP,
        reason=audit.Reason.SELF_SERVICE,
        event_type=audit.EventType.APP,
    ),
    autolog_config={
        "autoactor": get_user_from_resolver_args,
        "autostatus": True,
        "kwarg_name": "audit_msg",
    },
)

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


def is_valid_address(address):
    if not address:
        return False
    return address.get("city").upper() == "HELSINKI"


@query.field("getPermits")
@is_authenticated
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "User retrieved parking permits.",
        operation=audit.Operation.READ,
    ),
    autotarget=audit.TARGET_RETURN,
)
@transaction.atomic
def resolve_customer_permits(_obj, info):
    request = info.context["request"]
    # NOTE: get() actually fetches a *list* of items... and more importantly, also
    # deletes items. And also updates vehicles. So this is not purely a read operation.
    return CustomerPermit(request.user.customer.id).get()


def save_profile_address(address):
    address_obj = Address.objects.update_or_create(
        street_name=address.get("street_name"),
        street_number=address.get("street_number"),
        postal_code=address.get("postal_code"),
        defaults={
            "street_name": address.get("street_name"),
            "street_name_sv": address.get("street_name_sv"),
            "street_number": address.get("street_number"),
            "city": address.get("city"),
            "city_sv": address.get("city_sv"),
            "postal_code": address.get("postal_code"),
            "location": address.get("location"),
        },
    )
    return address_obj[0]


@query.field("profile")
@is_authenticated
@audit_logger.autolog(
    # Note: This resolver either updates or creates a profile,
    # so it's a read operation until a certain point.
    AuditMsg(
        "User retrieved user profile.",
        operation=audit.Operation.READ,
    ),
    autotarget=audit.TARGET_RETURN,
    add_kwarg=True,
)
@transaction.atomic
def resolve_user_profile(_obj, info, *args, audit_msg: AuditMsg = None):
    request = info.context["request"]
    profile = HelsinkiProfile(request)
    customer = profile.get_customer()
    primary_address_data, other_address_data = get_addresses(
        customer.get("national_id_number")
    )
    primary_address = (
        save_profile_address(primary_address_data)
        if is_valid_address(primary_address_data)
        else None
    )
    other_address = (
        save_profile_address(other_address_data)
        if is_valid_address(other_address_data)
        else None
    )

    customer_obj, created = Customer.objects.update_or_create(
        national_id_number=customer.get("national_id_number"),
        defaults={
            "user": request.user,
            **customer,
            **{"primary_address": primary_address, "other_address": other_address},
            "primary_address_apartment": primary_address_data.get("apartment")
            if is_valid_address(primary_address_data)
            else None,
            "primary_address_apartment_sv": primary_address_data.get("apartment_sv")
            if is_valid_address(primary_address_data)
            else None,
            "other_address_apartment": other_address_data.get("apartment")
            if is_valid_address(other_address_data)
            else None,
            "other_address_apartment_sv": other_address_data.get("apartment_sv")
            if is_valid_address(other_address_data)
            else None,
        },
    )

    if created:
        audit_msg.operation = audit.Operation.CREATE
        audit_msg.message = "User profile was created automatically."
    else:
        audit_msg.operation = audit.Operation.UPDATE
        audit_msg.message = "User profile was updated automatically."

    customer_obj.fetch_driving_licence_detail()
    return customer_obj


@mutation.field("updateLanguage")
@is_authenticated
@audit_logger.autolog(
    AuditMsg(
        "User updated language.",
        operation=audit.Operation.UPDATE,
    ),
    autotarget=audit.TARGET_RETURN,
)
@transaction.atomic
def resolve_update_language(_obj, info, lang):
    request = info.context["request"]
    customer = request.user.customer
    customer.language = lang
    customer.save()
    return customer


@address_node.field("primary")
@transaction.atomic
def resolve_address_primary(address, info):
    address_node_path_key = info.path.prev.key
    if address_node_path_key == "otherAddress":
        return False
    return True


def validate_customer_address(customer, address_id):
    """Check if the given address a valid customer address

    Customers can only update the permits to their only addresses,
    i.e. either the primary address or the other address
    """
    addr_ids = [customer.primary_address_id, customer.other_address_id]

    allowed_addr_ids = [str(addr_id) for addr_id in addr_ids if addr_id is not None]
    if address_id not in allowed_addr_ids:
        logger.error("Not a valid customer address")
        raise AddressError(_("Not a valid customer address"))

    try:
        return Address.objects.get(id=address_id)
    except Address.DoesNotExist:
        logger.error(f"updatePermitsAddress: address with id {address_id} not found")
        raise ObjectNotFound(_("Address not found"))


@query.field("getUpdateAddressPriceChanges")
@is_authenticated
@convert_kwargs_to_snake_case
@transaction.atomic
def resolve_get_update_address_price_changes(_obj, info, address_id):
    customer = info.context["request"].user.customer
    address = validate_customer_address(customer, address_id)
    new_zone = address.zone

    permits = ParkingPermit.objects.active().filter(customer=customer)
    if len(permits) == 0:
        logger.error(f"No active permits for the customer: {customer}")
        raise ObjectNotFound(_("No active permits for the customer"))

    permit_price_changes = []
    for permit in permits:
        permit_price_changes.append(
            {
                "permit": permit,
                "price_changes": permit.get_price_change_list(
                    new_zone, permit.vehicle.is_low_emission
                ),
            }
        )
    return permit_price_changes


@mutation.field("deleteParkingPermit")
@is_authenticated
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "User deleted parking permit.",
        operation=audit.Operation.DELETE,
    ),
    add_kwarg=True,
)
@transaction.atomic
def resolve_delete_parking_permit(_obj, info, permit_id, audit_msg: AuditMsg = None):
    # To avoid a database hit, we generate the target manually for the audit message.
    audit_msg.target = audit.ModelWithId(ParkingPermit, permit_id)
    request = info.context["request"]
    return CustomerPermit(request.user.customer.id).delete(permit_id)


@mutation.field("createParkingPermit")
@is_authenticated
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "User created parking permit.",
        operation=audit.Operation.CREATE,
    ),
    autotarget=audit.TARGET_RETURN,
)
@transaction.atomic
def resolve_create_parking_permit(_obj, info, address_id, registration):
    request = info.context["request"]
    return CustomerPermit(request.user.customer.id).create(address_id, registration)


@mutation.field("updateParkingPermit")
@is_authenticated
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "User updated parking permit.",
        operation=audit.Operation.UPDATE,
    ),
    add_kwarg=True,
)
@transaction.atomic
def resolve_update_parking_permit(
    _obj, info, input, permit_id=None, audit_msg: AuditMsg = None
):
    # This will get overwritten on a happy day scenario.
    audit_msg.target = [audit.ModelWithId(ParkingPermit, permit_id)]

    request = info.context["request"]
    results = CustomerPermit(request.user.customer.id).update(input, permit_id)
    audit_msg.target = results

    return results


@mutation.field("endParkingPermit")
@is_authenticated
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "User ended parking permits.",
        operation=audit.Operation.UPDATE,
    ),
    add_kwarg=True,
)
@transaction.atomic
def resolve_end_permit(
    _obj, info, permit_ids, end_type, iban=None, audit_msg: AuditMsg = None
):
    audit_msg.target = [
        audit.ModelWithId(ParkingPermit, permit_id) for permit_id in permit_ids
    ]
    request = info.context["request"]
    return CustomerPermit(request.user.customer.id).end(
        permit_ids, end_type, iban, request.user
    )


@mutation.field("getVehicleInformation")
@is_authenticated
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "User retrieved vehicle information.",
        operation=audit.Operation.READ,
    ),
    autotarget=audit.TARGET_RETURN,
)
@transaction.atomic
def resolve_get_vehicle_information(_obj, info, registration):
    request = info.context["request"]
    vehicle = Traficom().fetch_vehicle_details(registration_number=registration)
    customer = request.user.customer
    is_user_of_vehicle = customer.is_user_of_vehicle(vehicle)
    if not is_user_of_vehicle:
        raise TraficomFetchVehicleError(
            _("Owner/holder data of a vehicle could not be verified")
        )

    has_valid_licence = customer.has_valid_driving_licence_for_vehicle(vehicle)
    if not has_valid_licence:
        raise TraficomFetchVehicleError(
            _("Customer does not have a valid driving licence")
        )
    return vehicle


@mutation.field("updatePermitVehicle")
@is_authenticated
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "User changed parking permit's vehicle.",
        operation=audit.Operation.UPDATE,
    ),
    add_kwarg=True,
)
@transaction.atomic
def resolve_update_permit_vehicle(
    _obj,
    info,
    permit_id,
    vehicle_id,
    consent_low_emission_accepted=False,
    iban=None,
    audit_msg: AuditMsg = None,
):
    request = info.context["request"]
    customer = request.user.customer
    permit = ParkingPermit.objects.get(id=permit_id, customer=customer)
    old_registration_number = permit.vehicle.registration_number

    audit_msg.target = permit
    checkout_url = None
    talpa_order_created = False
    new_vehicle = Vehicle.objects.get(id=vehicle_id)
    new_vehicle.consent_low_emission_accepted = consent_low_emission_accepted
    new_vehicle.save()

    price_change_list = permit.get_price_change_list(
        permit.parking_zone, new_vehicle.is_low_emission
    )
    permit_total_price_change = sum(
        [item["price_change"] * item["month_count"] for item in price_change_list]
    )

    if permit_total_price_change > 0:
        permit.next_vehicle = new_vehicle
        permit.save()
    else:
        permit.vehicle = new_vehicle
        permit.save()

    new_order = Order.objects.create_renewal_order(
        customer,
        status=OrderStatus.CONFIRMED,
        order_type=OrderType.VEHICLE_CHANGED,
        payment_type=OrderPaymentType.ONLINE_PAYMENT,
        user=request.user,
        create_renew_order_event=permit_total_price_change > 0,
    )

    if permit_total_price_change < 0:
        refund = Refund.objects.create(
            name=customer.full_name,
            order=new_order,
            amount=-permit_total_price_change,
            iban=iban if iban else "",
            description=f"Refund for updating permits, customer switched vehicle to: {new_vehicle}",
        )
        refund.permits.add(permit)
        logger.info(f"Refund for updating permits created: {refund}")
        send_refund_email(RefundEmailType.CREATED, customer, refund)
        ParkingPermitEventFactory.make_create_refund_event(
            permit, refund, created_by=request.user
        )

    if permit_total_price_change > 0:
        checkout_url = TalpaOrderManager.send_to_talpa(new_order)
        permit.status = ParkingPermitStatus.PAYMENT_IN_PROGRESS
        talpa_order_created = True

    permit.vehicle_changed = False
    permit.vehicle_changed_date = None
    permit.save()

    ParkingPermitEventFactory.make_update_permit_event(
        permit,
        created_by=request.user,
        changes={"vehicle": [old_registration_number, new_vehicle.registration_number]},
    )

    if permit.contract_type == ContractType.OPEN_ENDED or not talpa_order_created:
        permit.update_parkkihubi_permit()
        send_permit_email(PermitEmailType.UPDATED, permit)

    return {"checkout_url": checkout_url}


@mutation.field("createOrder")
@is_authenticated
@audit_logger.autolog(
    AuditMsg(
        "User created an order for permits.",
        operation=audit.Operation.CREATE,
    ),
    add_kwarg=True,
)
@transaction.atomic
def resolve_create_order(_obj, info, audit_msg: AuditMsg = None):
    request = info.context["request"]
    customer = request.user.customer
    permits = ParkingPermit.objects.filter(
        customer=customer, status=ParkingPermitStatus.DRAFT
    )
    order = Order.objects.create_for_permits(permits, user=request.user)
    permits.update(status=ParkingPermitStatus.PAYMENT_IN_PROGRESS)
    audit_msg.target = order
    return {"checkout_url": TalpaOrderManager.send_to_talpa(order)}


@mutation.field("addTemporaryVehicle")
@is_authenticated
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "User added a temporary vehicle for a permit.",
        operation=audit.Operation.UPDATE,
    ),
    add_kwarg=True,
)
@transaction.atomic
def resolve_add_temporary_vehicle(
    _obj,
    info,
    permit_id,
    registration,
    start_time,
    end_time,
    audit_msg: AuditMsg = None,
):
    # To avoid a database hit, we generate the target manually for the audit message.
    audit_msg.target = audit.ModelWithId(ParkingPermit, permit_id)
    request = info.context["request"]
    customer = request.user.customer
    if tz.localtime(isoparse(start_time)) < tz.now():
        raise TemporaryVehicleValidationError(_("Start time cannot be in the past"))
    vehicle = Traficom().fetch_vehicle_details(registration_number=registration)
    has_valid_licence = customer.has_valid_driving_licence_for_vehicle(vehicle)
    if not has_valid_licence:
        raise TraficomFetchVehicleError(
            _("Customer does not have a valid driving licence for this vehicle")
        )
    CustomerPermit(request.user.customer.id).add_temporary_vehicle(
        permit_id, registration, start_time, end_time
    )
    return True


@mutation.field("removeTemporaryVehicle")
@is_authenticated
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "User removed a temporary vehicle for a permit.",
        operation=audit.Operation.UPDATE,
    ),
    add_kwarg=True,
)
@transaction.atomic
def resolve_remove_temporary_vehicle(_obj, info, permit_id, audit_msg: AuditMsg = None):
    # To avoid a database hit, we generate the target manually for the audit message.
    audit_msg.target = audit.ModelWithId(ParkingPermit, permit_id)
    request = info.context["request"]
    return CustomerPermit(request.user.customer.id).remove_temporary_vehicle(permit_id)


@mutation.field("changeAddress")
@is_authenticated
@convert_kwargs_to_snake_case
@audit_logger.autolog(
    AuditMsg(
        "User changed address.",
        operation=audit.Operation.UPDATE,
    ),
    add_kwarg=True,
)
@transaction.atomic
def resolve_change_address(
    _obj, info, address_id, iban=None, audit_msg: AuditMsg = None
):
    request = info.context["request"]
    customer = request.user.customer
    address = validate_customer_address(customer, address_id)
    new_zone = address.zone

    permits = ParkingPermit.objects.active().filter(customer=customer)
    if len(permits) == 0:
        logger.error(f"No active permits for the customer: {customer}")
        raise ObjectNotFound(_("No active permits for the customer"))

    audit_msg.target = permits

    # check that active permits are all in the same zone
    permit_zone_ids = [permit.parking_zone_id for permit in permits]
    if len(set(permit_zone_ids)) > 1:
        logger.error(
            f"updatePermitsAddress: active permits have conflict parking zones. Customer: {customer}"
        )
        raise ParkingZoneError(_("Conflict parking zones for active permits"))

    response = {"success": True}

    if permit_zone_ids[0] == new_zone.id:
        logger.info("No changes to the parking zone")
        return response

    fixed_period_permits = permits.fixed_period()
    if len(fixed_period_permits) > 0:
        # There can be two cases regarding customer's active permits:
        #
        # 1. A single permit or two permits are created at the same time.
        # In this case, there will be a single order for the permit[s],
        # and the total price changes for multiple permits are combined.
        # Only a single refund will be created if the price of the permits
        # goes down.
        #
        # 2. Two permits are created at different times.
        # In this case, permits will have different orders, and the total
        # price change need to be stored separately. We need to create
        # separate refunds also if the price of the permits goes down.
        #
        # The total_price_change_by_order Counter (with permit order as the key)
        # serves the purpose to combine the price change for multiple permits
        # if they belong to the same order and create separate entries otherwise.
        total_price_change_by_order = Counter()
        for permit in fixed_period_permits:
            price_change_list = permit.get_price_change_list(
                new_zone, permit.vehicle.is_low_emission
            )
            permit_total_price_change = sum(
                [
                    item["price_change"] * item["month_count"]
                    for item in price_change_list
                ]
            )
            total_price_change_by_order.update(
                {permit.latest_order: permit_total_price_change}
            )

        # total price changes for customer's all valid permits
        customer_total_price_change = sum(total_price_change_by_order.values())
        if customer_total_price_change > 0:
            # if price of the permits goes higher, the customer needs to make
            # extra payments through Talpa before the orders can be set to confirmed
            new_order_status = OrderStatus.DRAFT
            # update permit new zone to next parking zone and use that in price calculation
            fixed_period_permits.update(
                next_parking_zone=new_zone, next_address=address
            )
        else:
            new_order_status = OrderStatus.CONFIRMED
            old_zone_name = fixed_period_permits[0].parking_zone.name
            fixed_period_permits.update(parking_zone=new_zone, address=address)
            for permit in fixed_period_permits:
                ParkingPermitEventFactory.make_update_permit_event(
                    permit,
                    created_by=request.user,
                    changes={"parking_zone": [old_zone_name, new_zone.name]},
                )

        new_order = Order.objects.create_renewal_order(
            customer,
            status=new_order_status,
            order_type=OrderType.ADDRESS_CHANGED,
            payment_type=OrderPaymentType.ONLINE_PAYMENT,
            user=request.user,
            create_renew_order_event=customer_total_price_change > 0,
        )
        for order, order_total_price_change in total_price_change_by_order.items():
            # create refund for each order
            if order_total_price_change < 0:
                refund = Refund.objects.create(
                    name=customer.full_name,
                    order=order,
                    amount=-order_total_price_change,
                    iban=iban if iban else "",
                    description=f"Refund for updating permits zone (customer switch address to: {address})",
                )
                refund.permits.set(order.permits.all())
                logger.info(f"Refund for updating permits zone created: {refund}")
                send_refund_email(RefundEmailType.CREATED, customer, refund)
                for permit in order.permits.all():
                    ParkingPermitEventFactory.make_create_refund_event(
                        permit, refund, created_by=request.user
                    )

        if customer_total_price_change > 0:
            # go through talpa checkout process if the price of
            # the permits goes up
            response["checkout_url"] = TalpaOrderManager.send_to_talpa(new_order)
            fixed_period_permits.update(status=ParkingPermitStatus.PAYMENT_IN_PROGRESS)
        else:
            # Refresh the updated fixed-period permits and send email and update parkkihubi
            fixed_period_permits = permits.fixed_period().all()
            for permit in fixed_period_permits:
                permit.update_parkkihubi_permit()
                send_permit_email(PermitEmailType.UPDATED, permit)

    # For open ended permits, it's enough to update the permit zone
    # as talpa will get the updated price based on new zone when
    # asking permit price for next month
    open_ended_permits = permits.open_ended().all()
    for permit in open_ended_permits:
        with ModelDiffer(permit, fields=EventFields.PERMIT) as permit_diff:
            permit.parking_zone = new_zone
            permit.address = address
            permit.save()

        ParkingPermitEventFactory.make_update_permit_event(
            permit,
            created_by=request.user,
            changes=permit_diff,
        )

        permit.update_parkkihubi_permit()
        send_permit_email(PermitEmailType.UPDATED, permit)

    return response
