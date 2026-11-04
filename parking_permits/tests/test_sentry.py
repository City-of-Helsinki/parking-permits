import json
import logging
import runpy
from unittest.mock import patch

import environ
import pytest
import sentry_sdk
from django.test import Client, TestCase
from django.urls import reverse
from graphql import GraphQLError
from helusers.authz import UserAuthorization
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.transport import Transport

import parking_permits.decorators
from audit_logger.utils import EXCEPTION_SUMMARY_ATTR
from parking_permits.exceptions import (
    AddressError,
    DVVIntegrationError,
    ObjectNotFoundError,
    TraficomFetchVehicleError,
)
from parking_permits.models import ParkingPermit
from parking_permits.sentry import before_send, is_validation_error
from project import settings as project_settings
from project.settings import sentry_traces_sampler
from users.tests.factories.user import GroupFactory, UserFactory

EVENT = {"message": "test"}


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("configured", [False, True])
def test_sentry_initialization(monkeypatch, enabled, configured):
    for variable in (
        "SENTRY_ENVIRONMENT",
        "SENTRY_RELEASE",
        "SENTRY_TRACES_SAMPLE_RATE",
        "SENTRY_PROFILE_SESSION_SAMPLE_RATE",
        "SENTRY_TRACES_IGNORE_PATHS",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv(
        "SENTRY_DSN", "https://public@sentry.example.com/1" if enabled else ""
    )
    if configured:
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "testing")
        monkeypatch.setenv("SENTRY_RELEASE", "parking-permits@1.2.3")
        monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.25")
        monkeypatch.setenv("SENTRY_PROFILE_SESSION_SAMPLE_RATE", "0.5")
        monkeypatch.setenv("SENTRY_TRACES_IGNORE_PATHS", "/status")

    with (
        patch.object(environ.Env, "read_env"),
        patch.object(sentry_sdk, "init") as init,
    ):
        configuration = runpy.run_path(project_settings.__file__)

    if not enabled:
        init.assert_not_called()
        return

    init.assert_called_once()
    options = init.call_args.kwargs
    assert options["dsn"] == "https://public@sentry.example.com/1"
    assert options["environment"] == ("testing" if configured else "local")
    assert options["release"] == ("parking-permits@1.2.3" if configured else None)
    assert options["profile_session_sample_rate"] == (0.5 if configured else None)
    assert options["profile_lifecycle"] == "trace"
    assert options["before_send"] is before_send
    assert isinstance(options["integrations"][0], DjangoIntegration)
    sampler = options["traces_sampler"]
    assert sampler({}) == (0.25 if configured else 0.0)
    assert sampler({"wsgi_environ": {"PATH_INFO": "/status"}}) == 0.0
    assert configuration["SENTRY_TRACES_IGNORE_PATHS"] == (
        ["/status"] if configured else ["/healthz", "/readiness"]
    )


def test_sentry_cors_headers(settings):
    assert {"baggage", "sentry-trace", "x-authorization"} <= set(
        settings.CORS_ALLOW_HEADERS
    )


@pytest.mark.parametrize("sample_rate", [None, 0.0, 0.25, 1.0])
@pytest.mark.parametrize("parent_sampled", [None, False, True])
@pytest.mark.parametrize(
    "request_path",
    ["/healthz", "/healthz/", "/readiness", "/readiness/", "/graphql/", None],
)
def test_sentry_traces_sampler(monkeypatch, sample_rate, parent_sampled, request_path):
    monkeypatch.setattr("project.settings.SENTRY_TRACES_SAMPLE_RATE", sample_rate)
    monkeypatch.setattr(
        "project.settings.SENTRY_TRACES_IGNORE_PATHS", ["/healthz", "/readiness"]
    )
    context = {"parent_sampled": parent_sampled}
    if request_path is not None:
        context["wsgi_environ"] = {"PATH_INFO": request_path}

    if request_path in ["/healthz", "/healthz/", "/readiness", "/readiness/"]:
        expected = 0.0
    elif parent_sampled is not None:
        expected = float(parent_sampled)
    else:
        expected = sample_rate or 0.0

    assert sentry_traces_sampler(context) == expected


def test_sentry_traces_sampler_custom_ignore_paths(monkeypatch):
    monkeypatch.setattr("project.settings.SENTRY_TRACES_SAMPLE_RATE", 1.0)
    monkeypatch.setattr("project.settings.SENTRY_TRACES_IGNORE_PATHS", ["/status/"])

    assert sentry_traces_sampler({"wsgi_environ": {"PATH_INFO": "/status/"}}) == 0.0
    assert sentry_traces_sampler({"wsgi_environ": {"PATH_INFO": "/healthz"}}) == 1.0


def _exc_info(exc):
    return type(exc), exc, None


def _log_record(**extra):
    record = logging.LogRecord(
        name="audit",
        level=logging.ERROR,
        pathname=__file__,
        lineno=0,
        msg="Failed",
        args=(),
        exc_info=None,
    )
    record.__dict__.update(extra)
    return record


@pytest.mark.parametrize(
    "exc, expected",
    [
        (AddressError("Invalid address"), True),
        (ObjectNotFoundError(), True),
        (TraficomFetchVehicleError("No driving licence"), True),
        (GraphQLError("Wrapped", original_error=AddressError("Invalid")), True),
        (
            GraphQLError(
                "Nested",
                original_error=GraphQLError("Wrapped", original_error=AddressError()),
            ),
            True,
        ),
        (DVVIntegrationError("DVV error"), False),
        (ValueError("Unexpected"), False),
        (GraphQLError("Wrapped", original_error=ValueError("Unexpected")), False),
        (GraphQLError("Syntax error"), False),
        (None, False),
    ],
)
def test_is_validation_error(exc, expected):
    assert is_validation_error(exc) is expected


class TestBeforeSend:
    def test_drops_validation_error(self):
        hint = {"exc_info": _exc_info(AddressError("Invalid address"))}
        assert before_send(EVENT, hint) is None

    def test_drops_graphql_wrapped_validation_error(self):
        error = GraphQLError("Invalid", original_error=AddressError("Invalid"))
        assert before_send(EVENT, {"exc_info": _exc_info(error)}) is None

    def test_drops_validation_error_log_record(self):
        record = _log_record(**{EXCEPTION_SUMMARY_ATTR: "AddressError: Invalid"})
        assert before_send(EVENT, {"log_record": record}) is None

    def test_keeps_integration_error(self):
        hint = {"exc_info": _exc_info(DVVIntegrationError("DVV error"))}
        assert before_send(EVENT, hint) is EVENT

    def test_keeps_graphql_wrapped_unexpected_error(self):
        error = GraphQLError("Unexpected", original_error=ValueError("Unexpected"))
        assert before_send(EVENT, {"exc_info": _exc_info(error)}) is EVENT

    def test_keeps_unexpected_error_log_record(self):
        record = _log_record()
        record.exc_info = _exc_info(ValueError("Unexpected"))
        hint = {"exc_info": record.exc_info, "log_record": record}
        assert before_send(EVENT, hint) is EVENT

    def test_keeps_log_record_without_exception(self):
        assert before_send(EVENT, {"log_record": _log_record()}) is EVENT

    def test_keeps_event_without_hint_data(self):
        assert before_send(EVENT, {}) is EVENT


class CapturingTransport(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.events = []

    def capture_envelope(self, envelope):
        event = envelope.get_event()
        if event is not None:
            self.events.append(event)


extend_permit_mutation = """
    mutation ExtendPermit($permitId: ID!, $monthCount: Int) {
        extendPermit(permitId: $permitId, monthCount: $monthCount) {
            success
        }
    }
"""


def _exception_types(event):
    return [value["type"] for value in event.get("exception", {}).get("values", [])]


class SentryGraphQLErrorReportingTestCase(TestCase):
    """
    Run GraphQL requests with an active Sentry client, configured like in
    the settings, and check which events end up being sent to Sentry.
    """

    def setUp(self):
        self.transport = CapturingTransport()
        previous_client = sentry_sdk.get_client()
        sentry_sdk.init(
            dsn="https://public@sentry.example.com/1",
            transport=self.transport,
            integrations=[DjangoIntegration()],
            before_send=before_send,
        )
        self.addCleanup(sentry_sdk.get_global_scope().set_client, previous_client)

        isolation_scope = sentry_sdk.isolation_scope()
        isolation_scope.__enter__()
        self.addCleanup(isolation_scope.__exit__, None, None, None)

        admin = UserFactory()
        admin.groups.add(GroupFactory(name="super_admin"))
        authenticate_patcher = patch.object(
            parking_permits.decorators.RequestJWTAuthentication,
            "authenticate",
            return_value=UserAuthorization(admin, {}),
        )
        authenticate_patcher.start()
        self.addCleanup(authenticate_patcher.stop)

    def _extend_permit(self):
        response = Client().post(
            reverse("parking_permits:admin-graphql"),
            {
                "operationName": "ExtendPermit",
                "query": extend_permit_mutation,
                "variables": {"permitId": "999999", "monthCount": 1},
            },
            content_type="application/json",
        )
        sentry_sdk.flush()
        return json.loads(response.content)

    def test_validation_error_is_not_sent_to_sentry(self):
        response_data = self._extend_permit()

        # ObjectNotFoundError
        assert response_data["errors"]
        assert self.transport.events == []

    def test_unexpected_error_is_sent_to_sentry(self):
        with patch.object(
            ParkingPermit.objects, "active", side_effect=RuntimeError("Unexpected")
        ):
            response_data = self._extend_permit()

        assert response_data["errors"]
        assert self.transport.events
        assert all(
            "RuntimeError" in _exception_types(event) for event in self.transport.events
        )
