from audit_logger.tests.utils import make_mock_model
from audit_logger.utils import generate_model_identifier_string


def test_generate_model_identifier_string():
    MockModel = make_mock_model()
    SomeOtherModel = make_mock_model(name="SomeOtherModel")

    mock_model1 = MockModel()
    mock_model2 = MockModel()
    some_other_model_1 = SomeOtherModel()
    some_other_model_9000 = SomeOtherModel(id=9000)

    assert generate_model_identifier_string(mock_model1) == "mock_model__id__1"
    assert generate_model_identifier_string(mock_model2) == "mock_model__id__2"
    assert (
        generate_model_identifier_string(some_other_model_1)
        == "some_other_model__id__1"
    )
    assert (
        generate_model_identifier_string(some_other_model_9000)
        == "some_other_model__id__9000"
    )
