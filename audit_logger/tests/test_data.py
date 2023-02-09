import enum
from json import JSONDecoder
from unittest import mock

import freezegun
from django.utils import timezone

from audit_logger import AuditMessage, AuditType, EventType, Operation, Reason, Status
from audit_logger.data import AuditMessageEncoder, ModelWithId
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


@freezegun.freeze_time("2000-01-31 00:01:02.1234567", tz_offset=0)
@mock.patch(
    "audit_logger.data.generate_model_id_string_from_instance",
    return_value="id_from_instance",
)
@mock.patch(
    "audit_logger.data.generate_model_id_string_from_class",
    return_value="id_from_class",
)
def test_json_encoder(mock_gen_id_class, mock_gen_id_instance):
    class MyEnum(enum.Enum):
        FOO = "Foo"

    mock_model = MockModel()
    mock_model_class = mock_model.__class__
    d = dict(
        model=mock_model,
        model_with_id=ModelWithId(mock_model_class, 1),
        datetime=timezone.now(),
        enum=MyEnum.FOO,
    )

    output = JSONDecoder().decode(AuditMessageEncoder().encode(d))

    assert (
        dict(
            datetime="2000-01-31T00:01:02.123+00:00",
            enum="Foo",
            model="id_from_instance",
            model_with_id="id_from_class",
        )
        == output
    )
    mock_gen_id_class.assert_called_once_with(mock_model_class, 1)
    mock_gen_id_instance.assert_called_once_with(mock_model)


@mock.patch(
    "audit_logger.data.generate_model_id_string_from_instance",
    return_value="id_from_instance",
)
@mock.patch(
    "audit_logger.data.generate_model_id_string_from_class",
    return_value="id_from_class",
)
def test_json_encoder_with_multiple_models(*_):
    mock_model = MockModel()
    mock_model_class = mock_model.__class__
    d = dict(
        multiple_models=[
            MockModel(),
            MockModel(),
            ModelWithId(mock_model_class, 100),
            ModelWithId(mock_model_class, 9000),
        ]
    )

    output = JSONDecoder().decode(AuditMessageEncoder().encode(d))

    assert (
        dict(
            multiple_models=[
                "id_from_instance",
                "id_from_instance",
                "id_from_class",
                "id_from_class",
            ]
        )
        == output
    )
