import itertools
import logging
from contextlib import contextmanager

import freezegun
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from audit_logger import (
    TARGET_RETURN,
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
        logger = logging.getLogger("audit_logger")
        with self.assertLogs("audit_logger", logging.DEBUG) as cm, transaction.atomic():
            # Setup the logger.
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


class AdapterAutologTest(TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("audit_logger")
        self.logger.addHandler(AuditLogHandler())
        self.logger.setLevel(logging.DEBUG)
        self.adapter = AuditLoggerAdapter(self.logger, dict())

    def _first(self, cm):
        record: logging.LogRecord = cm.records[0]
        message: AuditMessage = record.msg
        return record, message

    @contextmanager
    def default_cm(self):
        with self.assertLogs("audit_logger", logging.DEBUG) as cm:
            yield cm

    def test_happy_day(self):
        @self.adapter.autolog(AuditMessage("Hello, world!"))
        def decorated_func():
            pass

        with self.default_cm() as cm:
            decorated_func()

        assert len(cm.records) == 1
        record, msg = self._first(cm)
        assert msg.message == "Hello, world!"
        assert record.levelno == logging.INFO

    def test_logs_on_error(self):
        @self.adapter.autolog(AuditMessage("Hello, world!"))
        def decorated_func():
            raise ValueError("Error")

        with self.default_cm() as cm:
            try:
                decorated_func()
            except ValueError:
                pass

        assert len(cm.records) == 1
        record, msg = self._first(cm)
        assert msg.message == "Hello, world!"
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None

    def test_autotarget(self):
        expected_target = MockModel()
        expected_args = ("foo", "bar")
        expected_kwargs = dict(kwarg="kwarg", something="something")

        def autotarget(return_val, *args, **kwargs):
            assert return_val == expected_target
            assert args == expected_args
            assert kwargs == expected_kwargs
            return return_val

        @self.adapter.autolog(AuditMessage(), autotarget=autotarget)
        def decorated_func(*_, **__):
            return expected_target

        with self.default_cm() as cm:
            decorated_func(*expected_args, **expected_kwargs)

        assert len(cm.records) == 1
        record, msg = self._first(cm)
        assert msg.target == expected_target

    def test_autoactor(self):
        expected_actor = MockModel()
        expected_args = (expected_actor, "foo", "bar")
        expected_kwargs = dict(kwarg="kwarg", something="something")

        def autoactor(*args, **kwargs):
            assert args == expected_args
            assert kwargs == expected_kwargs
            return args[0]

        @self.adapter.autolog(AuditMessage(), autoactor=autoactor)
        def decorated_func(*args, **kwargs):
            pass

        with self.default_cm() as cm:
            decorated_func(*expected_args, **expected_kwargs)

        assert len(cm.records) == 1
        record, msg = self._first(cm)
        assert msg.actor == expected_actor

    def test_autostatus_success(self):
        @self.adapter.autolog(AuditMessage(), autostatus=True)
        def decorated_func():
            pass

        with self.default_cm() as cm:
            decorated_func()

        assert len(cm.records) == 1
        record, msg = self._first(cm)
        assert msg.status == Status.SUCCESS

    def test_autostatus_failure(self):
        @self.adapter.autolog(AuditMessage(), autostatus=True)
        def decorated_func():
            raise ValueError

        with self.default_cm() as cm:
            try:
                decorated_func()
            except ValueError:
                pass

        assert len(cm.records) == 1
        record, msg = self._first(cm)
        assert msg.status == Status.FAILURE

    def test_multiple_decorated_calls_result_in_unique_audit_messages(self):
        with freezegun.freeze_time("1970-01-01"):
            base_datetime = timezone.now()
            base_msg = AuditMessage("The Original")

        counter = itertools.count(1)

        @self.adapter.autolog(base_msg, add_kwarg=True)
        def decorated_func(audit_msg):
            audit_msg.message = f"#{next(counter)}"

        with self.default_cm() as cm:
            with freezegun.freeze_time("1990-01-01"):
                expected_datetime1 = timezone.now()
                decorated_func()
            with freezegun.freeze_time("2000-01-01"):
                expected_datetime2 = timezone.now()
                decorated_func()

        assert len(cm.records) == 2

        msg1 = cm.records[0].msg
        msg2 = cm.records[1].msg

        assert msg1 != base_msg
        assert msg1.message == "#1"
        assert msg1.date_time == expected_datetime1

        assert msg2 != base_msg
        assert msg2.message == "#2"
        assert msg2.date_time == expected_datetime2

        # Make sure that the base message hasn't been modified as a side effect.
        assert base_msg.message == "The Original"
        assert base_msg.date_time == base_datetime

    def test_add_kwarg_bool(self):
        expected_message = "Hello, world!"

        @self.adapter.autolog(AuditMessage(), add_kwarg=True)
        def decorated_func(audit_msg=None):
            assert audit_msg is not None
            audit_msg.message = expected_message

        with self.default_cm() as cm:
            decorated_func()

        assert len(cm.records) == 1
        record, msg = self._first(cm)
        assert msg.message == expected_message

    def test_add_kwarg_str(self):
        expected_message = "Hello, world!"

        @self.adapter.autolog(AuditMessage(), add_kwarg="banana_hammock")
        def decorated_func(banana_hammock=None):
            assert banana_hammock is not None
            banana_hammock.message = expected_message

        with self.default_cm() as cm:
            decorated_func()

        assert len(cm.records) == 1
        record, msg = self._first(cm)
        assert msg.message == expected_message

    def test_add_kwarg_with_kwarg_name(self):
        expected_message = "Hello, world!"

        @self.adapter.autolog(AuditMessage(), add_kwarg=True, kwarg_name="noodles")
        def decorated_func(noodles=None):
            assert noodles is not None
            noodles.message = expected_message

        with self.default_cm() as cm:
            decorated_func()

        assert len(cm.records) == 1
        record, msg = self._first(cm)
        assert msg.message == expected_message

    def test_add_kwarg_str_with_kwarg_name(self):
        expected_message = "Hello, world!"

        @self.adapter.autolog(
            AuditMessage(), add_kwarg="banana_hammock", kwarg_name="noodles"
        )
        def decorated_func(banana_hammock=None, noodles=None):
            assert banana_hammock is not None
            assert noodles is None
            banana_hammock.message = expected_message

        with self.default_cm() as cm:
            decorated_func()

        assert len(cm.records) == 1
        record, msg = self._first(cm)
        assert msg.message == expected_message

    def test_auto_attributes_do_not_override_original_values(self):
        expected_target = MockModel()
        expected_actor = MockModel()
        expected_status = Status.FAILURE
        base_msg = AuditMessage(
            target=expected_target, actor=expected_actor, status=expected_status
        )

        def autoactor():
            new_actor = MockModel()
            assert expected_actor != new_actor  # Paranoia check
            return new_actor

        @self.adapter.autolog(
            base_msg, autostatus=True, autotarget=TARGET_RETURN, autoactor=autoactor
        )
        def decorated_func():
            new_target = MockModel
            assert expected_target != new_target  # Paranoia check
            return new_target

        with self.default_cm() as cm:
            decorated_func()

        assert len(cm.records) == 1
        record, msg = self._first(cm)
        assert msg != base_msg
        assert msg.target == expected_target
        assert msg.actor == expected_actor
        assert msg.status == expected_status
