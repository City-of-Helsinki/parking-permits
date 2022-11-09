from audit_logger import AuditMessage, AuditType, EventType, Operation, Status
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
