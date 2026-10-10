import json
import logging
from unittest.mock import patch

import pytest
from django.test import Client, TestCase
from django.urls import reverse
from graphql import GraphQLError
from helusers.authz import UserAuthorization
from resilient_logger.models import ResilientLogEntry
from resilient_logger.sources.resilient_log_source_entry import ResilientLogSourceEntry

import parking_permits.decorators
from audit_logger.utils import EXCEPTION_SUMMARY_ATTR
from parking_permits import exceptions
from parking_permits.exceptions import (
    AddressError,
    DVVIntegrationError,
    ParkingPermitBaseError,
    ParkingPermitValidationError,
)
from parking_permits.log_filters import ValidationErrorSummaryFilter
from users.tests.factories.user import GroupFactory, UserFactory

VALIDATION_ERRORS = [
    exceptions.AddressError,
    exceptions.CreatePermitError,
    exceptions.DeletionNotAllowedError,
    exceptions.DuplicatePermitError,
    exceptions.EndPermitError,
    exceptions.InvalidContractTypeError,
    exceptions.InvalidUserAddressError,
    exceptions.NonDraftPermitUpdateError,
    exceptions.ObjectNotFoundError,
    exceptions.ParkingZoneError,
    exceptions.PermitCanNotBeDeletedError,
    exceptions.PermitCanNotBeEndedError,
    exceptions.PermitCanNotBeExtendedError,
    exceptions.PermitLimitExceededError,
    exceptions.SearchError,
    exceptions.SubscriptionCancelError,
    exceptions.TemporaryVehicleValidationError,
    exceptions.TraficomFetchVehicleError,
    exceptions.UpdatePermitError,
]

NON_VALIDATION_ERRORS = [
    exceptions.CreateTalpaProductError,
    exceptions.CustomerCannotBeAnonymizedError,
    exceptions.DVVIntegrationError,
    exceptions.OrderCancelError,
    exceptions.OrderCreationFailedError,
    exceptions.OrderValidationError,
    exceptions.ParkkihubiPermitError,
    exceptions.PriceError,
    exceptions.ProductCatalogError,
    exceptions.RefundError,
    exceptions.SetTalpaFlowStepsError,
    exceptions.SubscriptionValidationError,
]


@pytest.mark.parametrize("exc_class", VALIDATION_ERRORS)
def test_validation_errors_are_parking_permit_validation_errors(exc_class):
    assert issubclass(exc_class, ParkingPermitValidationError)
    assert issubclass(exc_class, ParkingPermitBaseError)


@pytest.mark.parametrize("exc_class", NON_VALIDATION_ERRORS)
def test_non_validation_errors_are_not_parking_permit_validation_errors(exc_class):
    assert not issubclass(exc_class, ParkingPermitValidationError)
    assert issubclass(exc_class, ParkingPermitBaseError)


def _make_record(exc, msg=None):
    return logging.LogRecord(
        name="ariadne",
        level=logging.ERROR,
        pathname=__file__,
        lineno=0,
        msg=msg if msg is not None else exc,
        args=(),
        exc_info=(type(exc), exc, exc.__traceback__),
    )


def _raise(exc):
    try:
        raise exc
    except Exception as e:
        return e


def _graphql_error(original_error):
    # Mimic how GraphQL wraps exceptions raised in resolvers.
    return _raise(
        GraphQLError(str(original_error), original_error=_raise(original_error))
    )


class TestValidationErrorSummaryFilter:
    def test_strips_traceback_from_validation_error(self):
        error = _graphql_error(
            AddressError("Permit address does not have a valid zone")
        )
        record = _make_record(error)

        assert ValidationErrorSummaryFilter().filter(record) is record

        assert record.exc_info is None
        assert record.exc_text is None
        assert (
            record.getMessage()
            == "AddressError: Permit address does not have a valid zone"
        )
        assert (
            getattr(record, EXCEPTION_SUMMARY_ATTR)
            == "AddressError: Permit address does not have a valid zone"
        )

    def test_strips_traceback_from_unwrapped_validation_error(self):
        record = _make_record(_raise(AddressError("Invalid address")))

        assert ValidationErrorSummaryFilter().filter(record) is record

        assert record.exc_info is None
        assert record.getMessage() == "AddressError: Invalid address"
        assert (
            getattr(record, EXCEPTION_SUMMARY_ATTR) == "AddressError: Invalid address"
        )

    def test_keeps_traceback_for_integration_error(self):
        error = _graphql_error(DVVIntegrationError("DVV error"))
        record = _make_record(error)

        assert ValidationErrorSummaryFilter().filter(record) is record

        assert record.exc_info is not None
        assert record.exc_info[1] is error
        assert record.msg is error
        assert not hasattr(record, EXCEPTION_SUMMARY_ATTR)

    def test_keeps_traceback_for_unexpected_error(self):
        error = _graphql_error(ValueError("Unexpected"))
        record = _make_record(error)

        assert ValidationErrorSummaryFilter().filter(record) is record

        assert record.exc_info is not None
        assert record.msg is error
        assert not hasattr(record, EXCEPTION_SUMMARY_ATTR)

    def test_passes_records_without_exception(self):
        record = logging.LogRecord(
            name="ariadne",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg="Hello %s",
            args=("world",),
            exc_info=None,
        )

        assert ValidationErrorSummaryFilter().filter(record) is record

        assert record.getMessage() == "Hello world"


extend_permit_mutation = """
    mutation ExtendPermit($permitId: ID!, $monthCount: Int) {
        extendPermit(permitId: $permitId, monthCount: $monthCount) {
            success
        }
    }
"""


class AdminGraphQLValidationErrorLoggingTestCase(TestCase):
    @patch.object(parking_permits.decorators.RequestJWTAuthentication, "authenticate")
    def test_validation_error_is_logged_without_traceback(self, mock_authenticate):
        admin = UserFactory()
        admin.groups.add(GroupFactory(name="super_admin"))
        mock_authenticate.return_value = UserAuthorization(admin, {})

        data = {
            "operationName": "ExtendPermit",
            "query": extend_permit_mutation,
            "variables": {"permitId": "999999", "monthCount": 1},
        }

        with self.assertLogs("ariadne", logging.ERROR) as cm:
            response = Client().post(
                reverse("parking_permits:admin-graphql"),
                data,
                content_type="application/json",
            )

        response_data = json.loads(response.content)
        assert response_data["errors"]

        # Ariadne's GraphQL error log
        assert len(cm.records) == 1
        ariadne_record = cm.records[0]
        assert ariadne_record.exc_info is None
        assert ariadne_record.getMessage() == (
            "ObjectNotFoundError (caused by DoesNotExist: "
            "ParkingPermit matching query does not exist.)"
        )

        # Audit log
        entry = ResilientLogEntry.objects.get()
        trace = ResilientLogSourceEntry(entry).get_document()["audit_event"]["extra"][
            "trace"
        ]
        assert "Traceback" not in trace
        assert trace == (
            "ObjectNotFoundError (caused by DoesNotExist: "
            "ParkingPermit matching query does not exist.)"
        )
