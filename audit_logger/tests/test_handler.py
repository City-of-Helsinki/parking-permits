import logging

import pytest

from audit_logger import enums
from audit_logger.data import AuditMessage
from audit_logger.db_log_handler import AuditLogHandler
from audit_logger.models import AuditLog
from audit_logger.tests.utils import MockLogRecord, make_mock_model

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
        audit_msg = make_audit_msg(log_level=enums.AuditLogLevel.DEBUG)
        record = MockLogRecord(msg=audit_msg)

        created_audit_msg = AuditLogHandler.makeAuditMessage(record)

        assert created_audit_msg == audit_msg

    def test_should_get_log_level_from_record_if_not_set_in_message(
        self, make_audit_msg
    ):
        audit_msg = make_audit_msg()
        record = MockLogRecord(msg=audit_msg, levelno=logging.DEBUG)

        created_audit_msg = AuditLogHandler.makeAuditMessage(record)

        assert created_audit_msg.log_level == enums.AuditLogLevel.DEBUG

    def test_should_raise_error_with_non_audit_message_message(self, make_audit_msg):
        audit_msg = make_audit_msg()
        record = MockLogRecord(msg=audit_msg.asdict(), levelno=logging.DEBUG)

        with pytest.raises(TypeError) as excinfo:
            AuditLogHandler.makeAuditMessage(record)

        assert "must be an AuditMessage" in str(excinfo.value)


@pytest.mark.django_db
def test_should_create_audit_log_from_record(make_audit_msg):
    audit_msg = make_audit_msg(actor=Actor(), target=Target())
    record = MockLogRecord(msg=audit_msg, levelno=logging.DEBUG)
    record.name = "audit_logger"
    try:
        1 / 0
    except Exception as exc_info:
        record.exc_info = (type(exc_info), exc_info, exc_info.__traceback__)

    created_audit_log = AuditLogHandler.createAuditLogFromRecord(record)
    assert len(AuditLog.objects.all()) == 1
    assert AuditLog.objects.first() == created_audit_log
    assert "ZeroDivisionError" in created_audit_log.trace
