import pytest

from audit_logger.tests.utils import make_mock_model
from audit_logger.utils import (
    format_exception_summary,
    generate_model_id_string_from_class,
    generate_model_id_string_from_instance,
)


class CustomError(Exception):
    pass


def test_format_exception_summary():
    assert (
        format_exception_summary(CustomError("Something is invalid"))
        == "CustomError: Something is invalid"
    )


def test_format_exception_summary_without_message():
    assert format_exception_summary(CustomError()) == "CustomError"


def test_format_exception_summary_includes_explicit_cause():
    try:
        try:
            raise KeyError("missing")
        except KeyError as e:
            raise CustomError from e
    except CustomError as e:
        exc = e

    assert (
        format_exception_summary(exc) == "CustomError (caused by KeyError: 'missing')"
    )


def test_format_exception_summary_has_no_traceback():
    try:
        raise CustomError("Something is invalid")
    except CustomError as e:
        exc = e

    summary = format_exception_summary(exc)

    assert "Traceback" not in summary
    assert "\n" not in summary


def test_generate_model_instance_id_string():
    mock_model = make_mock_model()
    some_other_model = make_mock_model(name="SomeOtherModel")

    mock_model1 = mock_model()
    mock_model2 = mock_model()
    some_other_model_1 = some_other_model()
    some_other_model_9000 = some_other_model(id=9000)

    assert generate_model_id_string_from_instance(mock_model1) == "mock_model__id__1"
    assert generate_model_id_string_from_instance(mock_model2) == "mock_model__id__2"
    assert (
        generate_model_id_string_from_instance(some_other_model_1)
        == "some_other_model__id__1"
    )
    assert (
        generate_model_id_string_from_instance(some_other_model_9000)
        == "some_other_model__id__9000"
    )


def test_generate_model_id_string_from_class():
    mock_model = make_mock_model()
    some_other_model = make_mock_model(name="some_other_model")

    # We need to create an instance of the mock models and use their __class__ here.
    # Because of mock reasons.
    assert (
        generate_model_id_string_from_class(mock_model().__class__, 1)
        == "mock_model__id__1"
    )
    assert (
        generate_model_id_string_from_class(some_other_model().__class__, 9000)
        == "some_other_model__id__9000"
    )


def test_generate_model_id_string_from_class_should_raise_error_if_not_model_class():
    mock_model = make_mock_model()

    class Foo:
        pass

    # With a model instance
    with pytest.raises(TypeError):
        generate_model_id_string_from_class(mock_model(), 1)

    # With a class other than a Model
    with pytest.raises(TypeError):
        generate_model_id_string_from_class(Foo, 1)
