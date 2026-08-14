from ai_test_case_generator.models import GenerationRequest, UserStory
from ai_test_case_generator.requirements import (
    requirement_prompt_data,
    requirement_text_by_id,
)


def make_request(*criteria: str) -> GenerationRequest:
    return GenerationRequest(
        story=UserStory(
            id="US-001",
            title="Reset a password",
            narrative="As a user, I want to reset my password.",
            acceptance_criteria=list(criteria),
        )
    )


def test_acceptance_criteria_receive_stable_ordered_ids() -> None:
    request = make_request("First criterion.", "Second criterion.")

    assert requirement_text_by_id(request) == {
        "AC-001": "First criterion.",
        "AC-002": "Second criterion.",
    }
    assert requirement_prompt_data(request) == [
        {"id": "AC-001", "text": "First criterion."},
        {"id": "AC-002", "text": "Second criterion."},
    ]


def test_narrative_receives_a_stable_fallback_id() -> None:
    request = make_request()

    assert requirement_text_by_id(request) == {
        "NARRATIVE": "As a user, I want to reset my password."
    }
