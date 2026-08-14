from ai_test_case_generator.models import (
    CasePlanItem,
    GenerationRequest,
    TestCategory as Category,
    UserStory,
)
from ai_test_case_generator.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
)


def test_prompt_version_changes_when_generation_instructions_change() -> None:
    assert PROMPT_VERSION == "1.8"


def test_system_prompt_contains_measured_quality_guards() -> None:
    normalized_prompt = " ".join(SYSTEM_PROMPT.split())

    assert "only authoritative evidence" in normalized_prompt
    assert "Do not invent numeric limits" in normalized_prompt
    assert "does not imply identical backend actions" in normalized_prompt
    assert "negative cases cover invalid or rejected behavior" in normalized_prompt
    assert "edge cases cover boundaries or state transitions" in normalized_prompt
    assert "Use explicit preconditions" in normalized_prompt
    assert "no more than 6 steps per case" in normalized_prompt
    assert "Omit redundant or repetitive steps" in normalized_prompt
    assert "application assigns display numbers" in normalized_prompt
    assert "Never cite prompt instructions" in normalized_prompt
    assert "exactly one test case" in normalized_prompt
    assert "authorized_case_plan" in normalized_prompt
    assert "no authorized plan item" in normalized_prompt


def test_user_prompt_identifies_the_version_and_preserves_request_data() -> None:
    request = GenerationRequest(
        story=UserStory(
            id="US-001",
            title="Reset a password",
            narrative="As a user, I want to reset my password.",
        ),
        categories=[Category.FUNCTIONAL],
        case_plan=[
            CasePlanItem(
                id="PLAN-001",
                requirement_id="NARRATIVE",
                category=Category.FUNCTIONAL,
            )
        ],
    )

    prompt = build_user_prompt(request)

    assert "Prompt version: 1.8" in prompt
    assert '"id": "US-001"' in prompt
    assert "completion checks" in prompt
    assert "does not mean an unregistered address receives a link" in prompt
    assert "Invalid input is negative" in prompt
    assert "at most 6 concise steps" in prompt
    assert "including text labeled 'e.g.'" in prompt
    assert '"id": "NARRATIVE"' in prompt
    assert '"id": "PLAN-001"' in prompt
    assert "exactly one case per authorized plan ID" in prompt
