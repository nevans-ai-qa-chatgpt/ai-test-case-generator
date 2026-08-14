import pytest
from pydantic import ValidationError

from ai_test_case_generator.model_output import (
    ModelCoverageGap,
    ModelTestCase,
    ModelTestStep,
    ModelTestSuite,
    model_output_json_schema,
)
from ai_test_case_generator.models import (
    CasePlanItem,
    GenerationRequest,
    Priority,
    TestCategory as Category,
    UserStory,
)


def make_request() -> GenerationRequest:
    return GenerationRequest(
        story=UserStory(
            id="US-001",
            title="Reset a password",
            narrative="As a user, I want to reset my password.",
            acceptance_criteria=["A registered user receives a reset link."],
        ),
        categories=[Category.FUNCTIONAL],
        case_plan=[
            CasePlanItem(
                id="PLAN-001",
                requirement_id="AC-001",
                category=Category.FUNCTIONAL,
            )
        ],
    )


def make_model_case() -> ModelTestCase:
    return ModelTestCase(
        id="TC-001",
        plan_id="PLAN-001",
        title="Reset a password",
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
        tags=["password-reset"],
    )


def test_model_output_assigns_step_numbers_from_list_order() -> None:
    model_suite = ModelTestSuite(
        source_story_id="US-001",
        test_cases=[make_model_case()],
    )

    suite = model_suite.to_test_suite(make_request())

    assert [step.number for step in suite.test_cases[0].steps] == [1, 2]
    assert [step.action for step in suite.test_cases[0].steps] == [
        "Request a reset link.",
        "Open the reset link.",
    ]
    assert suite.test_cases[0].source_requirements == [
        "A registered user receives a reset link."
    ]
    assert suite.test_cases[0].category is Category.FUNCTIONAL
    assert suite.test_cases[0].plan_id == "PLAN-001"


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
    assert case_properties["plan_id"]["pattern"]
    assert "category" not in case_properties
    assert "source_requirement_ids" not in case_properties


def test_request_schema_allows_only_the_authorized_plan_and_count() -> None:
    request = make_request()

    schema = model_output_json_schema(request)
    plan_id = schema["$defs"]["ModelTestCase"]["properties"]["plan_id"]

    assert plan_id == {
        "type": "string",
        "enum": ["PLAN-001"],
    }
    assert schema["properties"]["test_cases"]["minItems"] == 1
    assert schema["properties"]["test_cases"]["maxItems"] == 1
    assert schema["properties"]["coverage_gaps"]["maxItems"] == 0


def test_model_case_requires_preconditions() -> None:
    case_data = make_model_case().model_dump(mode="json")
    case_data["preconditions"] = []

    with pytest.raises(ValidationError, match="at least 1 item"):
        ModelTestCase.model_validate(case_data)


def test_model_case_rejects_an_invalid_plan_id() -> None:
    case_data = make_model_case().model_dump(mode="json")
    case_data["plan_id"] = ""

    with pytest.raises(ValidationError, match="String should match pattern"):
        ModelTestCase.model_validate(case_data)


def test_unknown_plan_id_cannot_be_converted() -> None:
    unknown_case = make_model_case().model_copy(
        update={"plan_id": "PLAN-999"}
    )
    model_suite = ModelTestSuite(
        source_story_id="US-001",
        test_cases=[unknown_case],
    )

    with pytest.raises(ValueError, match="authorized case plan"):
        model_suite.to_test_suite(make_request())


def test_model_can_abstain_for_an_unsupported_category() -> None:
    request = make_request().model_copy(
        update={"categories": [Category.FUNCTIONAL, Category.EDGE]}
    )
    model_suite = ModelTestSuite(
        source_story_id="US-001",
        test_cases=[make_model_case()],
        coverage_gaps=[
            ModelCoverageGap(
                category=Category.EDGE,
                reason="No boundary behavior is specified.",
            )
        ],
    )

    suite = model_suite.to_test_suite(request)

    assert len(suite.test_cases) == 1
    assert suite.coverage_gaps[0].category is Category.EDGE


def test_model_cannot_return_a_case_and_gap_for_the_same_category() -> None:
    model_suite = ModelTestSuite(
        source_story_id="US-001",
        test_cases=[make_model_case()],
        coverage_gaps=[
            ModelCoverageGap(
                category=Category.FUNCTIONAL,
                reason="No supported behavior.",
            )
        ],
    )

    with pytest.raises(ValueError, match="required coverage gaps"):
        model_suite.to_test_suite(make_request())
