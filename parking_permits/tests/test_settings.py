import os
import re
import subprocess
import sys

import pytest

from project.settings import parse_cors_allowed_origin_regexes


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    "environment",
    ["", "local", "development", "review", "testing", "staging", "production"],
)
def test_local_admin_roles_environment_guard(enabled, environment):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from project import settings; "
            f"assert settings.LOCAL_ADMIN_ROLES_ENABLED is {enabled!r}",
        ],
        env={
            **os.environ,
            "LOCAL_ADMIN_ROLES_ENABLED": str(enabled),
            "DEPLOYMENT_ENVIRONMENT": environment,
            "DEBUG": "True",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    if not enabled or environment in {"development", "review"}:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert "ImproperlyConfigured" in result.stderr
        assert "LOCAL_ADMIN_ROLES_ENABLED requires" in result.stderr


def test_local_admin_roles_default_to_disabled():
    environment = os.environ.copy()
    environment.pop("LOCAL_ADMIN_ROLES_ENABLED", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from unittest.mock import patch; "
            "patch('environ.Env.read_env').start(); "
            "from project import settings; "
            "assert settings.LOCAL_ADMIN_ROLES_ENABLED is False",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


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
