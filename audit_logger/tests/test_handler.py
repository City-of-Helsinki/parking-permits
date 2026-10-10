import logging

import pytest
from resilient_logger.models import ResilientLogEntry
from resilient_logger.sources.resilient_log_source_entry import ResilientLogSourceEntry

from audit_logger import enums
from audit_logger.data import AuditMessage
from audit_logger.db_log_handler import AuditLogHandler
from audit_logger.tests.utils import make_mock_model, mock_log_record
from audit_logger.utils import EXCEPTION_SUMMARY_ATTR

Actor = make_mock_model(name="Actor")
Target = make_mock_model(name="Target")


@pytest.fixture
def make_audit_msg():
    def _make_audit_msg(**kwargs):
        default_kwargs = dict(
            message="message",
            actor=Actor(),
            target=Target(),
            reason=enums.Reason.SELF_SERVICE,
            operation=enums.Operation.READ,
            status=enums.Status.SUCCESS,
        )
        return AuditMessage(**default_kwargs | kwargs)

    return _make_audit_msg


class TestMakeAuditMessage:
    def test_should_make_audit_message_with_audit_message(self, make_audit_msg):
        audit_msg = make_audit_msg(log_level=logging.DEBUG)
        record = mock_log_record(msg=audit_msg)

        created_audit_msg = AuditLogHandler.make_audit_message(record)

        assert created_audit_msg == audit_msg

    def test_should_get_log_level_from_record_if_not_set_in_message(
        self, make_audit_msg
    ):
        audit_msg = make_audit_msg()
        record = mock_log_record(msg=audit_msg, levelno=logging.DEBUG)

        created_audit_msg = AuditLogHandler.make_audit_message(record)

        assert created_audit_msg.log_level == logging.DEBUG

    def test_should_raise_error_with_non_audit_message_message(self, make_audit_msg):
        audit_msg = make_audit_msg()
        record = mock_log_record(msg=audit_msg.asdict(), levelno=logging.DEBUG)

        with pytest.raises(TypeError) as excinfo:
            AuditLogHandler.make_audit_message(record)

        assert "must be an AuditMessage" in str(excinfo.value)


@pytest.mark.django_db
def test_should_create_audit_log_from_record(make_audit_msg):
    audit_msg = make_audit_msg(actor=Actor(), target=Target())
    record = mock_log_record(msg=audit_msg, levelno=logging.DEBUG)
    record.name = "audit_logger"
    try:
        1 / 0  # noqa: B018
    except Exception as exc_info:
        record.exc_info = (type(exc_info), exc_info, exc_info.__traceback__)

    created_audit_log = AuditLogHandler.create_audit_log_from_record(record)
    created_document = created_audit_log.get_document()

    assert len(ResilientLogEntry.objects.all()) == 1
    assert (
        ResilientLogSourceEntry(ResilientLogEntry.objects.first()).get_document()
        == created_document
    )
    assert "ZeroDivisionError" in created_document["audit_event"]["extra"]["trace"]


@pytest.mark.django_db
def test_should_create_audit_log_with_exception_summary_as_trace(make_audit_msg):
    audit_msg = make_audit_msg(status=enums.Status.FAILURE)
    record = logging.LogRecord(
        name="audit_logger",
        level=logging.ERROR,
        pathname=__file__,
        lineno=0,
        msg=audit_msg,
        args=(),
        exc_info=None,
    )
    setattr(record, EXCEPTION_SUMMARY_ATTR, "AddressError: Invalid address")

    created_audit_log = AuditLogHandler.create_audit_log_from_record(record)
    created_document = created_audit_log.get_document()

    assert (
        created_document["audit_event"]["extra"]["trace"]
        == "AddressError: Invalid address"
    )


@pytest.mark.django_db
def test_should_create_audit_log_without_trace(make_audit_msg):
    audit_msg = make_audit_msg()
    record = logging.LogRecord(
        name="audit_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=audit_msg,
        args=(),
        exc_info=None,
    )

    created_audit_log = AuditLogHandler.create_audit_log_from_record(record)
    created_document = created_audit_log.get_document()

    assert created_document["audit_event"]["extra"]["trace"] is None
