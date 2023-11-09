class ParkingPermitEndType:
    IMMEDIATELY = "IMMEDIATELY"
    AFTER_CURRENT_PERIOD = "AFTER_CURRENT_PERIOD"


SECONDARY_VEHICLE_PRICE_INCREASE = 50
VAT_PERCENTAGE = 24


class Origin:
    ADMIN_UI = "parking-permits-admin-ui"
    WEBSHOP = "parking-permits-ui"


class EventFields:
    """Default ModelDiffer fields, used for parking permit events."""

    VEHICLE = ("registration_number",)
    PERMIT = ("status",)
    CUSTOMER = (
        "first_name",
        "last_name",
        "phone_number",
        "email",
        "primary_address",
        "other_address",
        "zone",
    )
