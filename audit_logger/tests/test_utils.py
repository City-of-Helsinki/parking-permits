import pytest

from audit_logger.tests.utils import make_mock_model
from audit_logger.utils import (
    generate_model_id_string_from_class,
    generate_model_id_string_from_instance,
)


def test_generate_model_instance_id_string():
    MockModel = make_mock_model()
    SomeOtherModel = make_mock_model(name="SomeOtherModel")

    mock_model1 = MockModel()
    mock_model2 = MockModel()
    some_other_model_1 = SomeOtherModel()
    some_other_model_9000 = SomeOtherModel(id=9000)

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
    MockModel = make_mock_model()
    SomeOtherModel = make_mock_model(name="SomeOtherModel")

    # We need to create an instance of the mock models and use their __class__ here.
    # Because of mock reasons.
    assert (
        generate_model_id_string_from_class(MockModel().__class__, 1)
        == "mock_model__id__1"
    )
    assert (
        generate_model_id_string_from_class(SomeOtherModel().__class__, 9000)
        == "some_other_model__id__9000"
    )


def test_generate_model_id_string_from_class_should_raise_error_if_not_model_class():
    MockModel = make_mock_model()

    class Foo:
        pass

    # With a model instance
    with pytest.raises(TypeError):
        generate_model_id_string_from_class(MockModel(), 1)

    # With a class other than a Model
    with pytest.raises(TypeError):
        generate_model_id_string_from_class(Foo, 1)
