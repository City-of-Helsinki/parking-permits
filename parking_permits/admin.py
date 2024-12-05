from django.contrib.admin.sites import NotRegistered
from django.contrib.gis import admin
from django.urls import reverse
from django.utils.html import format_html
from django_db_logger.models import StatusLog

from parking_permits.models import (
    Address,
    Announcement,
    Company,
    Customer,
    DrivingClass,
    DrivingLicence,
    LowEmissionCriteria,
    Order,
    OrderItem,
    ParkingPermit,
    ParkingPermitExtensionRequest,
    ParkingZone,
    Product,
    Refund,
    Subscription,
    TemporaryVehicle,
    Vehicle,
)
from parking_permits.models.parking_permit import ParkingPermitEvent
from parking_permits.models.product import Accounting
from parking_permits.models.vehicle import VehiclePowerType, VehicleUser


@admin.register(Address)
class AddressAdmin(admin.GISModelAdmin):
    search_fields = (
        "id",
        "street_name",
        "street_name_sv",
        "city",
        "city_sv",
        "postal_code",
    )
    list_display = (
        "id",
        "street_name",
        "street_name_sv",
        "street_number",
        "postal_code",
        "city",
        "city_sv",
    )
    ordering = (
        "street_name",
        "street_number",
        "city",
    )


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    search_fields = ("id", "subject_en", "subject_fi", "subject_sv")
    list_display = (
        "id",
        "subject_en",
        "subject_fi",
        "subject_sv",
        "created_at",
        "created_by",
    )
    ordering = ("-created_at",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    search_fields = ("name", "business_id")
    list_display = ("id", "name", "business_id", "address", "company_owner")
    list_select_related = ("address", "company_owner")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    search_fields = (
        "id",
        "first_name",
        "last_name",
        "national_id_number",
        "email",
    )
    list_display = (
        "__str__",
        "id",
        "first_name",
        "last_name",
        "email",
        "full_primary_address",
        "full_other_address",
    )
    ordering = (
        "first_name",
        "last_name",
    )


@admin.register(DrivingClass)
class DrivingClassAdmin(admin.ModelAdmin):
    list_display = ("identifier",)


@admin.register(DrivingLicence)
class DrivingLicenceAdmin(admin.ModelAdmin):
    search_fields = (
        "customer__first_name",
        "customer__last_name",
        "customer__national_id_number",
    )
    list_display = ("id", "customer", "start_date", "end_date", "active")
    list_select_related = ("customer",)


@admin.register(VehiclePowerType)
class VehiclePowerTypeAdmin(admin.ModelAdmin):
    list_display = (
        "identifier",
        "name",
    )


@admin.register(LowEmissionCriteria)
class LowEmissionCriteriaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nedc_max_emission_limit",
        "wltp_max_emission_limit",
        "euro_min_class_limit",
        "start_date",
        "end_date",
    )
    ordering = ("start_date",)


@admin.register(ParkingPermit)
class ParkingPermitAdmin(admin.ModelAdmin):
    search_fields = (
        "pk",
        "customer__first_name",
        "customer__last_name",
        "customer__national_id_number",
        "vehicle__registration_number",
    )
    list_display = (
        "id",
        "customer",
        "vehicle",
        "parking_zone",
        "full_address",
        "full_address_sv",
        "status",
        "start_time",
        "end_time",
        "contract_type",
    )
    list_filter = ("contract_type", "status")
    list_select_related = ("customer", "vehicle", "parking_zone")
    ordering = (
        "customer__first_name",
        "customer__last_name",
    )
    raw_id_fields = (
        "address",
        "customer",
        "vehicle",
        "next_vehicle",
        "temp_vehicles",
    )
    readonly_fields = ("latest_order",)

    @admin.display()
    def latest_order(self, instance):
        order = instance.latest_order
        url = reverse("admin:parking_permits_order_change", args=[order.pk])
        return format_html('<a href="{}">{}</a>', url, order)


@admin.register(ParkingPermitEvent)
class ParkingPermitEventAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    search_fields = (
        "parking_permit__id",
        "parking_permit__customer__first_name",
        "parking_permit__customer__last_name",
        "parking_permit__customer__national_id_number",
    )
    ordering = ("-created_at",)
    list_display = ("parking_permit", "key", "type", "created_at")
    list_filter = ("key", "type")
    raw_id_fields = (
        "created_by",
        "modified_by",
    )


@admin.register(ParkingZone)
class ParkingZoneAdmin(admin.GISModelAdmin):
    search_fields = ("name", "description", "description_sv")
    list_display = ("id", "name", "description", "description_sv")
    ordering = ("name",)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    search_fields = ("registration_number", "manufacturer", "model")
    list_display = (
        "id",
        "registration_number",
        "manufacturer",
        "model",
    )
    ordering = ("registration_number",)
    raw_id_fields = ("users",)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["users"].required = False
        form.base_fields["restrictions"].required = False
        return form


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    search_fields = ("name", "iban", "orders__id")
    list_display = (
        "name",
        "iban",
        "get_orders",
        "amount",
        "status",
        "created_at",
        "accepted_at",
        "get_vat_percent",
    )
    ordering = ("-created_at",)
    raw_id_fields = (
        "accepted_by",
        "created_by",
        "modified_by",
        "orders",
        "permits",
    )

    @admin.display(description="Orders")
    def get_orders(self, obj):
        return ", ".join([str(order.id) for order in obj.orders.all()])

    @admin.display(description="VAT percent")
    def get_vat_percent(self, obj):
        return format(obj.vat_percent, ".2f")


@admin.register(Accounting)
class AccountingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "active_from",
        "company_code",
        "vat_code",
        "internal_order",
        "profit_center",
        "balance_profit_center",
        "project",
        "operation_area",
        "main_ledger_account",
    )
    ordering = ("-created_at",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    search_fields = ("zone__name",)
    list_display = (
        "zone",
        "type",
        "start_date",
        "end_date",
        "unit_price",
        "low_emission_discount_percentage",
        "talpa_product_id",
        "accounting",
        "next_accounting",
    )
    list_select_related = ("zone",)
    readonly_fields = ("talpa_product_id",)
    ordering = (
        "zone__name",
        "start_date",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    search_fields = (
        "id",
        "customer__last_name",
        "customer__first_name",
        "customer__national_id_number",
        "talpa_order_id",
        "vehicles",
    )
    list_filter = ("status", "type")
    list_display = (
        "id",
        "customer",
        "status",
        "total_payment_price",
        "address_text",
        "parking_zone_name",
        "vehicles",
        "get_vat_percents",
        "talpa_order_id",
    )
    list_select_related = ("customer",)
    readonly_fields = (
        "talpa_order_id",
        "total_payment_price",
        "get_vat_percents",
    )
    raw_id_fields = (
        "customer",
        "created_by",
        "modified_by",
        "permits",
    )
    ordering = ("-created_at",)

    @admin.display(description="Vat percents")
    def get_vat_percents(self, obj):
        return (
            ", ".join([format(vat * 100, ".2f") for vat in obj.vat_values])
            if obj.vat_values
            else None
        )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    search_fields = (
        "id",
        "order__id",
        "talpa_order_item_id",
        "order__talpa_order_id",
        "subscription__talpa_subscription_id",
        "permit__id",
    )
    raw_id_fields = ("permit", "order", "product", "subscription")
    list_display = (
        "id",
        "order",
        "subscription",
        "product",
        "permit",
        "unit_price",
        "payment_unit_price",
        "quantity",
        "get_vat_percent",
        "talpa_order_item_id",
    )
    list_select_related = ("order", "subscription", "product", "permit")
    readonly_fields = ("talpa_order_item_id",)
    ordering = ("-pk",)

    @admin.display(description="Vat percent")
    def get_vat_percent(self, obj):
        return format(obj.vat_percentage, ".2f")


@admin.register(ParkingPermitExtensionRequest)
class ParkingPermitExtensionRequestAdmin(admin.ModelAdmin):
    search_fields = (
        "permit__id",
        "permit__customer__first_name",
        "permit__customer__last_name",
        "permit__vehicle__registration_number",
    )
    raw_id_fields = ("permit", "order")
    list_filter = ("status",)
    ordering = ("-created_at",)
    list_display = ("permit", "status", "month_count")
    list_select_related = True


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    search_fields = (
        "id",
        "talpa_subscription_id",
        "order_items__talpa_order_item_id",
    )
    list_filter = ("status",)
    list_display = (
        "id",
        "talpa_subscription_id",
        "get_talpa_order_item_id",
        "status",
        "cancel_reason",
        "created_by",
        "created_at",
    )
    readonly_fields = (
        "talpa_subscription_id",
        "get_talpa_order_item_id",
    )
    ordering = ("-created_at",)

    @admin.display(description="Talpa order item id")
    def get_talpa_order_item_id(self, obj):
        if obj.order_items.exists():
            return obj.order_items.first().talpa_order_item_id


@admin.register(TemporaryVehicle)
class TemporaryVehicleAdmin(admin.ModelAdmin):
    search_fields = ("id", "vehicle__registration_number")
    list_display = (
        "id",
        "vehicle",
        "start_time",
        "end_time",
        "is_active",
    )
    ordering = ("vehicle",)


@admin.register(VehicleUser)
class VehicleUserAdmin(admin.ModelAdmin):
    search_fields = (
        "national_id_number",
        "vehicles__registration_number",
    )
    list_display = ("national_id_number", "get_vehicles")
    ordering = ("national_id_number",)

    @admin.display(description="Vehicles")
    def get_vehicles(self, obj):
        return [vehicle.registration_number for vehicle in obj.vehicles.all()]


# Importing the default StatusLogAdmin will automatically register the StatusLog model
from django_db_logger.admin import StatusLogAdmin  # noqa: F401, E402

# Unregister the StatusLog model from the admin site registry
try:
    admin.site.unregister(StatusLog)
except NotRegistered:
    pass


# Create application specific StatusLogAdmin
@admin.register(StatusLog)
class ParkingPermitsStatusLogAdmin(StatusLogAdmin):
    search_fields = ("msg",)  # Add search field for the message
    list_per_page = 30
