import pytest
from pydantic import ValidationError

from ai_test_case_generator.model_output import (
    ModelTestCase,
    ModelTestStep,
    ModelTestSuite,
)
from ai_test_case_generator.models import Priority, TestCategory as Category


def make_model_case() -> ModelTestCase:
    return ModelTestCase(
        id="TC-001",
        title="Reset a password",
        category=Category.FUNCTIONAL,
        priority=Priority.HIGH,
        objective="Verify the reset workflow.",
        preconditions=["A registered account exists."],
        steps=[
            ModelTestStep(
                action="Request a reset link.",
                expected_result="The request is accepted.",
            ),
            ModelTestStep(
                action="Open the reset link.",
                expected_result="The password form is displayed.",
            ),
        ],
        source_requirements=["A registered user receives a reset link."],
        tags=["password-reset"],
    )


def test_model_output_assigns_step_numbers_from_list_order() -> None:
    model_suite = ModelTestSuite(
        source_story_id="US-001",
        test_cases=[make_model_case()],
    )

    suite = model_suite.to_test_suite()

    assert [step.number for step in suite.test_cases[0].steps] == [1, 2]
    assert [step.action for step in suite.test_cases[0].steps] == [
        "Request a reset link.",
        "Open the reset link.",
    ]


def test_model_step_schema_does_not_accept_a_number() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ModelTestStep.model_validate(
            {
                "number": 99,
                "action": "Request a reset link.",
                "expected_result": "The request is accepted.",
            }
        )


def test_model_schema_preserves_generation_bounds() -> None:
    schema = ModelTestSuite.model_json_schema()

    assert schema["properties"]["test_cases"]["maxItems"] == 6
    assert schema["$defs"]["ModelTestCase"]["properties"]["steps"]["maxItems"] == 6
    assert "number" not in schema["$defs"]["ModelTestStep"]["properties"]
    case_properties = schema["$defs"]["ModelTestCase"]["properties"]
    assert case_properties["preconditions"]["minItems"] == 1
    assert case_properties["source_requirements"]["minItems"] == 1


@pytest.mark.parametrize("field_name", ["preconditions", "source_requirements"])
def test_model_case_requires_grounding_metadata(field_name: str) -> None:
    case_data = make_model_case().model_dump(mode="json")
    case_data[field_name] = []

    with pytest.raises(ValidationError, match="at least 1 item"):
        ModelTestCase.model_validate(case_data)
