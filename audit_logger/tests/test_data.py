import freezegun

from audit_logger import AuditMessage, AuditType, EventType, Operation, Reason, Status
from audit_logger.tests.utils import make_mock_model

MockModel = make_mock_model()


def test_audit_msg_set_defaults():
    msg = AuditMessage(
        "My message",
        actor=MockModel(),
        target=MockModel(),
        operation=Operation.CREATE,
        status=Status.SUCCESS,
        event_type=EventType.HELSINKI_PROFILE,
        audit_type=AuditType.AUDIT,
    )
    msg.set_defaults(
        origin="foo",
        version="v9000",
        event_type=EventType.TALPA,
        status=Status.FAILURE,
        audit_type=AuditType.APP,
    )

    # Attributes that should change
    # No init value, field default is None
    assert msg.origin == "foo"
    # No init value, field default something else than None
    assert msg.version == "v9000"
    # Has init value, init value == field default
    assert msg.audit_type == AuditType.APP

    # Attributes that shouldn't change
    # Has init value, field default is None
    assert msg.status == Status.SUCCESS
    # Has init value, init value != field default
    assert msg.event_type == EventType.HELSINKI_PROFILE


def test_asdict():
    audit_msg_kwargs = dict(
        message="My message",
        actor=MockModel(id=1),
        target=MockModel(id=2),
        operation=Operation.CREATE,
        reason=Reason.SELF_SERVICE,
        status=Status.SUCCESS,
        event_type=EventType.HELSINKI_PROFILE,
        audit_type=AuditType.AUDIT,
        origin="foo",
        version="v9000",
    )

    with freezegun.freeze_time("2001-01-01"):
        msg = AuditMessage(**audit_msg_kwargs)

    with freezegun.freeze_time("2002-02-02"):
        d = msg.asdict()

    # All the data should remain the same.
    for k in audit_msg_kwargs.keys():
        assert d[k] == getattr(msg, k)

    # Model fields should still refer to the same object.
    assert d["actor"] is msg.actor
    assert d["target"] is msg.target

    # Creation timestamp shouldn't change.
    assert d["date_time"] == msg.date_time
