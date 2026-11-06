import re

import pytest

from project.settings import parse_cors_allowed_origin_regexes


@pytest.mark.parametrize(
    "value",
    [
        "[",
        '"["',
        '["^https://example[.]com$", "["]',
    ],
)
def test_parse_cors_allowed_origin_regexes_rejects_invalid_patterns(value):
    with pytest.raises(re.error):
        parse_cors_allowed_origin_regexes(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", []),
        ('""', []),
        ("^https://example[.]com$", ["^https://example[.]com$"]),
        ('"^https://example[.]com$"', ["^https://example[.]com$"]),
        (
            '["^https://example[.]com$", "^http://localhost$"]',
            ["^https://example[.]com$", "^http://localhost$"],
        ),
    ],
)
def test_parse_cors_allowed_origin_regexes_returns_valid_patterns(value, expected):
    assert parse_cors_allowed_origin_regexes(value) == expected
