import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_test_case_generator.models import (
    Priority,
    TestCase as CaseModel,
    TestCategory as Category,
    TestStep as StepModel,
    TestSuite as SuiteModel,
    UserStory,
)


def make_test_case(*, case_id: str = "TC-001") -> CaseModel:
    return CaseModel(
        id=case_id,
        title="Registered user requests a password reset",
        category=Category.FUNCTIONAL,
        priority=Priority.HIGH,
        objective="Verify that a registered user can request a reset link.",
        preconditions=["A registered account exists."],
        steps=[
            StepModel(
                number=1,
                action="Submit the registered email address.",
                expected_result="A generic confirmation message is displayed.",
            )
        ],
        source_requirements=["A registered user receives a time-limited link."],
        tags=["password-reset", "authentication"],
    )


def test_user_story_strips_surrounding_whitespace() -> None:
    story = UserStory(id=" US-001 ", title=" Reset password ", narrative=" Story ")

    assert story.id == "US-001"
    assert story.title == "Reset password"


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        UserStory(id="US-001", title="Reset password", narrative="Story", owner="QA")


def test_steps_must_start_at_one_and_be_consecutive() -> None:
    with pytest.raises(ValidationError, match="consecutively"):
        CaseModel(
            id="TC-001",
            title="Invalid numbering",
            category=Category.NEGATIVE,
            priority=Priority.MEDIUM,
            objective="Demonstrate validation.",
            steps=[
                StepModel(number=1, action="First action", expected_result="First result"),
                StepModel(number=3, action="Third action", expected_result="Third result"),
            ],
        )


def test_test_case_ids_must_be_unique_within_a_suite() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        SuiteModel(
            source_story_id="US-001",
            test_cases=[make_test_case(), make_test_case()],
        )


def test_valid_suite_serializes_to_json_compatible_data() -> None:
    suite = SuiteModel(source_story_id="US-001", test_cases=[make_test_case()])

    result = suite.model_dump(mode="json")

    assert result["schema_version"] == "1.0"
    assert result["test_cases"][0]["category"] == "functional"
    assert result["test_cases"][0]["steps"][0]["number"] == 1


def test_documented_example_matches_the_domain_contract() -> None:
    example_path = Path(__file__).parents[1] / "examples" / "password_reset.json"
    example = json.loads(example_path.read_text(encoding="utf-8"))

    story = UserStory.model_validate(example["input"])
    suite = SuiteModel.model_validate(example["example_output"])

    assert suite.source_story_id == story.id


def test_evaluation_baseline_matches_the_domain_contract() -> None:
    baseline_path = (
        Path(__file__).parents[1]
        / "evals"
        / "baselines"
        / "password_reset_prompt_v1.0.json"
    )

    suite = SuiteModel.model_validate_json(
        baseline_path.read_text(encoding="utf-8")
    )

    assert suite.source_story_id == "US-001"
    assert len(suite.test_cases) == 6


@pytest.mark.parametrize(
    "filename",
    [
        "password_reset_prompt_v1.1.json",
        "password_reset_prompt_v1.2.json",
    ],
)
def test_evaluation_experiment_matches_the_domain_contract(filename: str) -> None:
    experiment_path = (
        Path(__file__).parents[1] / "evals" / "experiments" / filename
    )

    suite = SuiteModel.model_validate_json(
        experiment_path.read_text(encoding="utf-8")
    )

    assert suite.source_story_id == "US-001"
