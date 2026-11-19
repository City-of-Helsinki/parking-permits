from django.core.validators import validate_email


def clean_email(value):
    """Return the stripped email address, or "" if empty; raise if invalid."""
    value = (value or "").strip()
    if value:
        validate_email(value)
    return value
