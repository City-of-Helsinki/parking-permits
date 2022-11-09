import logging

from django.db import transaction
from django.test import TestCase

from audit_logger import (
    AuditLoggerAdapter,
    AuditLogHandler,
    AuditLogLevel,
    AuditMessage,
    AuditMsg,
    AuditType,
    EventType,
    Operation,
    Reason,
    Status,
    getAuditLoggerAdapter,
)
from audit_logger.models import AuditLog
from audit_logger.tests.utils import make_mock_model

MockModel = make_mock_model()


class AuditLoggerTest(TestCase):
    def test_usage(self):
        """Doesn't really test much, more of a showcase of how it works."""
        with self.assertLogs("audit_logger", logging.DEBUG) as cm, transaction.atomic():
            # Setup the logger.
            logger = logging.getLogger("audit_logger")
            logger.addHandler(AuditLogHandler())
            logger.setLevel(logging.DEBUG)

            # Let's make some log records!
            logger.debug(
                AuditMsg(
                    "This is a debug message, with minimal parameters",
                    actor=MockModel(),
                    target=MockModel(),
                    reason=Reason.SELF_SERVICE,
                    operation=Operation.READ,
                    status=Status.SUCCESS,
                )
            )
            logger.info(
                AuditMessage(
                    "This is an info message, with all of the parameters",
                    actor=MockModel(),
                    target=MockModel(),
                    reason=Reason.SELF_SERVICE,
                    operation=Operation.CREATE,
                    audit_type=AuditType.AUDIT,
                    event_type=EventType.TALPA,
                    status=Status.SUCCESS,
                    origin="unit-test",
                    version="v9000",
                )
            )
            logger.warning(
                AuditMsg(
                    "This will show up as an error in the audit log but warning in the database",
                    actor=MockModel(),
                    target=MockModel(),
                    reason=Reason.SELF_SERVICE,
                    operation=Operation.DELETE,
                    status=Status.SUCCESS,
                )
            )
            logger.error(
                AuditMsg(
                    "This is an error message",
                    actor=MockModel(),
                    target=MockModel(),
                    reason=Reason.SELF_SERVICE,
                    operation=Operation.DELETE,
                    status=Status.FAILURE,
                )
            )
            try:
                1 / 0
            except Exception as e:
                logger.critical(
                    AuditMsg(
                        "This is an error message with traceback",
                        actor=MockModel(),
                        target=MockModel(),
                        reason=Reason.MAINTENANCE,
                        operation=Operation.UPDATE,
                        status=Status.SUCCESS,
                    ),
                    exc_info=e,
                )
                logger.exception(
                    AuditMsg(
                        "This is an error message with traceback",
                        actor=MockModel(),
                        target=MockModel(),
                        reason=Reason.MAINTENANCE,
                        operation=Operation.UPDATE,
                        status=Status.SUCCESS,
                    )
                )

        assert len(cm.records) == 6
        assert len(AuditLog.objects.all()) == 6
        assert len(AuditLog.objects.filter(message__log_level=AuditLogLevel.ERROR)) == 4
        assert len(AuditLog.objects.filter(level__gte=logging.WARNING)) == 4

    def test_logger_adapter(self):
        with self.assertLogs("audit_logger", logging.DEBUG) as cm, transaction.atomic():
            # Setup the logger.
            logger = logging.getLogger("audit_logger")
            logger.addHandler(AuditLogHandler())
            logger.setLevel(logging.DEBUG)
            adapter = AuditLoggerAdapter(logger, {"origin": "foo"})

            adapter.info(
                AuditMessage(
                    "Hello world!",
                    actor=MockModel(),
                    target=MockModel(),
                    operation=Operation.CREATE,
                    status=Status.SUCCESS,
                )
            )

        assert len(cm.records) == 1
        assert cm.records[0].msg.origin == "foo"

    def test_get_logger_adapter(self):
        with self.assertLogs("audit_logger", logging.DEBUG) as cm, transaction.atomic():
            # Setup the logger.
            adapter = getAuditLoggerAdapter("audit_logger", dict(origin="foo"))
            adapter.logger.addHandler(AuditLogHandler())
            adapter.logger.setLevel(logging.DEBUG)

            adapter.info(
                AuditMessage(
                    "Hello world!",
                    actor=MockModel(),
                    target=MockModel(),
                    operation=Operation.CREATE,
                    status=Status.SUCCESS,
                )
            )

        assert len(cm.records) == 1
        assert cm.records[0].msg.origin == "foo"
