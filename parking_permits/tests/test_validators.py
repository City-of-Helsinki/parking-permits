import pytest
from django.core.exceptions import ValidationError

from parking_permits.models import Customer
from parking_permits.validators import clean_email

INVALID_EMAILS = [
    "a@example.com.",
    "a@example.",
    "a@example",
    "a b@example.com",
    "example.com",
    "@example.com",
]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  ", ""),
        ("a@example.com", "a@example.com"),
        ("  a@example.com ", "a@example.com"),
    ],
)
def test_clean_email_normalizes(value, expected):
    assert clean_email(value) == expected


@pytest.mark.parametrize("email", INVALID_EMAILS)
def test_clean_email_rejects_invalid(email):
    with pytest.raises(ValidationError):
        clean_email(email)


def test_customer_email_field_validates():
    with pytest.raises(ValidationError):
        Customer._meta.get_field("email").run_validators("a@example.com.")
