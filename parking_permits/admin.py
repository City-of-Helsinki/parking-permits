from django.contrib.gis import admin

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
    ParkingZone,
    Product,
    Refund,
    Subscription,
    TemporaryVehicle,
    Vehicle,
)
from parking_permits.models.vehicle import VehiclePowerType, VehicleUser


@admin.register(Address)
class AddressAdmin(admin.OSMGeoAdmin):
    search_fields = ("street_name", "street_name_sv", "city", "city_sv")
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
    search_fields = ("first_name", "last_name")
    list_display = ("__str__", "id", "first_name", "last_name", "email")
    ordering = (
        "first_name",
        "last_name",
    )


@admin.register(DrivingClass)
class DrivingClassAdmin(admin.ModelAdmin):
    list_display = ("identifier",)


@admin.register(DrivingLicence)
class DrivingLicenceAdmin(admin.ModelAdmin):
    search_fields = ("customer__first_name", "customer__last_name")
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
    search_fields = ("customer__first_name", "customer__last_name")
    list_display = (
        "id",
        "customer",
        "vehicle",
        "parking_zone",
        "address",
        "status",
        "start_time",
        "end_time",
        "contract_type",
    )
    list_select_related = ("customer", "vehicle", "parking_zone")
    ordering = (
        "customer__first_name",
        "customer__last_name",
    )


@admin.register(ParkingZone)
class ParkingZoneAdmin(admin.OSMGeoAdmin):
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


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "iban",
        "order",
        "amount",
        "status",
        "created_at",
        "accepted_at",
    )
    list_select_related = ("order",)
    ordering = ("-created_at",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "zone",
        "type",
        "start_date",
        "end_date",
        "unit_price",
        "low_emission_discount_percentage",
        "talpa_product_id",
    )
    list_select_related = ("zone",)
    readonly_fields = ("talpa_product_id",)
    ordering = (
        "zone__name",
        "start_date",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_filter = ("status",)
    list_display = (
        "id",
        "customer",
        "status",
        "total_payment_price",
        "address_text",
        "parking_zone_name",
        "vehicles",
    )
    list_select_related = ("customer",)
    readonly_fields = (
        "talpa_order_id",
        "total_payment_price",
    )
    ordering = ("-created_at",)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "subscription",
        "product",
        "permit",
        "unit_price",
        "payment_unit_price",
        "quantity",
    )
    list_select_related = ("order", "subscription", "product", "permit")
    readonly_fields = ("talpa_order_item_id",)
    ordering = ("-pk",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
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
    list_display = (
        "vehicle",
        "start_time",
        "end_time",
        "is_active",
    )
    ordering = ("vehicle",)


@admin.register(VehicleUser)
class VehicleUserAdmin(admin.ModelAdmin):
    list_display = ("national_id_number", "get_vehicles")
    ordering = ("national_id_number",)

    @admin.display(description="Vehicles")
    def get_vehicles(self, obj):
        return [vehicle.registration_number for vehicle in obj.vehicles.all()]
