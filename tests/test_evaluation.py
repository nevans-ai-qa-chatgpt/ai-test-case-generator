from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_test_case_generator.evaluation import (
    EvaluationCase,
    EvaluationDataset,
    load_evaluation_dataset,
)
from ai_test_case_generator.models import (
    GenerationRequest,
    TestCategory as Category,
    UserStory,
)


DATASET_PATH = Path(__file__).parents[1] / "evals" / "dataset.json"


def make_case(*, case_id: str, story_id: str) -> EvaluationCase:
    return EvaluationCase(
        id=case_id,
        purpose="Exercise a representative generation behavior.",
        request=GenerationRequest(
            story=UserStory(
                id=story_id,
                title="Representative story",
                narrative="As a user, I want representative behavior.",
            )
        ),
        review_assertions=["The result stays grounded in the story."],
        forbidden_assumptions=["An unspecified product rule."],
        tags=["grounding"],
    )


def test_representative_dataset_matches_the_evaluation_contract() -> None:
    dataset = load_evaluation_dataset(DATASET_PATH)

    assert dataset.schema_version == "1.0"
    assert len(dataset.cases) == 8
    assert {
        category for case in dataset.cases for category in case.request.categories
    } == set(Category)
    assert all(case.request.case_plan for case in dataset.cases)


def test_representative_dataset_varies_risk_and_requirement_density() -> None:
    dataset = load_evaluation_dataset(DATASET_PATH)
    tags = {tag for case in dataset.cases for tag in case.tags}

    assert {
        "security",
        "boundary",
        "authorization",
        "daylight-saving",
        "calculation",
        "sparse-requirements",
    } <= tags
    assert any(not case.request.story.acceptance_criteria for case in dataset.cases)
    assert any(len(case.request.categories) == 1 for case in dataset.cases)


def test_evaluation_case_review_metadata_must_be_unique() -> None:
    case = make_case(case_id="EVAL-001", story_id="US-EVAL-001")

    with pytest.raises(ValidationError, match="review_assertions must contain unique"):
        EvaluationCase.model_validate(
            {
                **case.model_dump(mode="json"),
                "review_assertions": ["Repeated assertion", "Repeated assertion"],
            }
        )


def test_evaluation_case_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="evaluation case IDs must be unique"):
        EvaluationDataset(
            cases=[
                make_case(case_id="EVAL-001", story_id="US-EVAL-001"),
                make_case(case_id="EVAL-001", story_id="US-EVAL-002"),
            ]
        )


def test_evaluation_story_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="evaluation story IDs must be unique"):
        EvaluationDataset(
            cases=[
                make_case(case_id="EVAL-001", story_id="US-EVAL-001"),
                make_case(case_id="EVAL-002", story_id="US-EVAL-001"),
            ]
        )
