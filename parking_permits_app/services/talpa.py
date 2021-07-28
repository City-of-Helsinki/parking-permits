import uuid

from parking_permits_app.constants import VAT_PERCENTAGE
from parking_permits_app.pricing.value_added_tax import calculate_price_without_vat


def get_meta_value(meta_pair_list, meta_pair_key):
    return next(
        (
            meta_pair.get("value")
            for meta_pair in meta_pair_list
            if meta_pair.get("key") == meta_pair_key
        ),
        None,
    )


def resolve_price_response(product_id=None, total_price=None):
    net_value = calculate_price_without_vat(total_price)
    vat_value = total_price - net_value

    return {
        "productId": product_id,
        "original": {
            "price": {
                "netValue": str(net_value),
                "vatPercentage": str(VAT_PERCENTAGE),
                "grossValue": str(total_price),
                "vatValue": str(vat_value),
            }
        },
    }


def resolve_availability_response(product_id=None, availability=None):
    return {
        "productId": product_id,
        "value": availability,
    }


def resolve_right_of_purchase_response(product_id=None, right_of_purchase=None):
    return {
        "productId": product_id,
        "value": right_of_purchase,
    }


def is_valid_uuid(uuid_value):
    try:
        uuid.UUID(uuid_value)
        return True
    except ValueError:
        return False
