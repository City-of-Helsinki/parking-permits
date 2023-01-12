import pytest

from parking_permits.talpa.order import TalpaOrderManager


@pytest.mark.parametrize(
    "value, expected",
    [
        (1.0, "1"),
        (1.01, "1"),
        (1.499999, "1"),
        (1.5, "2"),
    ],
)
def test_round_int(value, expected):
    assert TalpaOrderManager.round_int(value) == expected
