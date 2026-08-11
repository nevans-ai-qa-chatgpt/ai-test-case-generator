import pytest
from pydantic import ValidationError

from ai_test_case_generator.models import (
    GenerationRequest,
    TestCategory as Category,
    UserStory,
)
from ai_test_case_generator.providers import (
    FakeTestCaseProvider,
    TestCaseProvider as ProviderContract,
)


def make_story(*, acceptance_criteria: list[str] | None = None) -> UserStory:
    return UserStory(
        id="US-001",
        title="Reset a forgotten password",
        narrative="As a user, I want to reset my password to regain access.",
        acceptance_criteria=acceptance_criteria or [],
    )


def test_fake_provider_satisfies_the_provider_contract() -> None:
    assert isinstance(FakeTestCaseProvider(), ProviderContract)


def test_default_request_generates_one_case_per_category() -> None:
    request = GenerationRequest(story=make_story())

    suite = FakeTestCaseProvider().generate(request)

    assert [case.id for case in suite.test_cases] == ["TC-001", "TC-002", "TC-003"]
    assert [case.category for case in suite.test_cases] == list(Category)


def test_requested_category_order_is_preserved() -> None:
    request = GenerationRequest(
        story=make_story(),
        categories=[Category.EDGE, Category.FUNCTIONAL],
    )

    suite = FakeTestCaseProvider().generate(request)

    assert [case.category for case in suite.test_cases] == [
        Category.EDGE,
        Category.FUNCTIONAL,
    ]


def test_generation_is_deterministic() -> None:
    request = GenerationRequest(story=make_story())
    provider = FakeTestCaseProvider()

    assert provider.generate(request) == provider.generate(request)


def test_acceptance_criteria_are_used_for_traceability() -> None:
    requirement = "A registered user receives a time-limited reset link."
    request = GenerationRequest(story=make_story(acceptance_criteria=[requirement]))

    suite = FakeTestCaseProvider().generate(request)

    assert all(case.source_requirements == [requirement] for case in suite.test_cases)


def test_narrative_is_traceability_fallback() -> None:
    story = make_story()

    suite = FakeTestCaseProvider().generate(GenerationRequest(story=story))

    assert all(case.source_requirements == [story.narrative] for case in suite.test_cases)


def test_duplicate_requested_categories_are_rejected() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        GenerationRequest(
            story=make_story(),
            categories=[Category.FUNCTIONAL, Category.FUNCTIONAL],
        )
