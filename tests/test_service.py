from dataclasses import dataclass

import pytest

from ai_test_case_generator.models import (
    GenerationRequest,
    Priority,
    TestCase as CaseModel,
    TestCategory as Category,
    TestStep as StepModel,
    TestSuite as SuiteModel,
    UserStory,
)
from ai_test_case_generator.providers import FakeTestCaseProvider
from ai_test_case_generator.service import GenerationService, ProviderContractError


@dataclass
class StubProvider:
    suite: SuiteModel
    name: str = "stub"

    def generate(self, request: GenerationRequest) -> SuiteModel:
        return self.suite


def make_request(*categories: Category) -> GenerationRequest:
    story = UserStory(
        id="US-001",
        title="Reset a forgotten password",
        narrative="As a user, I want to reset my password to regain access.",
    )
    selected = list(categories) if categories else list(Category)
    return GenerationRequest(story=story, categories=selected)


def make_case(case_id: str, category: Category) -> CaseModel:
    return CaseModel(
        id=case_id,
        title=f"A {category.value} test",
        category=category,
        priority=Priority.MEDIUM,
        objective="Exercise the requested behavior.",
        steps=[
            StepModel(
                number=1,
                action="Perform an action.",
                expected_result="Observe the result.",
            )
        ],
    )


def make_suite(story_id: str, *categories: Category) -> SuiteModel:
    return SuiteModel(
        source_story_id=story_id,
        test_cases=[
            make_case(f"TC-{index:03d}", category)
            for index, category in enumerate(categories, start=1)
        ],
    )


def test_fake_provider_passes_the_strict_service_contract() -> None:
    request = make_request()
    service = GenerationService(FakeTestCaseProvider())

    suite = service.generate(request)

    assert service.provider_name == "fake"
    assert suite.source_story_id == request.story.id


def test_wrong_source_story_is_rejected() -> None:
    request = make_request(Category.FUNCTIONAL)
    provider = StubProvider(make_suite("US-999", Category.FUNCTIONAL))

    with pytest.raises(ProviderContractError, match="expected 'US-001'"):
        GenerationService(provider).generate(request)


def test_missing_requested_category_is_rejected() -> None:
    request = make_request(Category.FUNCTIONAL, Category.NEGATIVE)
    provider = StubProvider(make_suite("US-001", Category.FUNCTIONAL))

    with pytest.raises(ProviderContractError, match="missing categories: negative"):
        GenerationService(provider).generate(request)


def test_unrequested_category_is_rejected() -> None:
    request = make_request(Category.FUNCTIONAL)
    provider = StubProvider(
        make_suite("US-001", Category.FUNCTIONAL, Category.EDGE)
    )

    with pytest.raises(ProviderContractError, match="unexpected categories: edge"):
        GenerationService(provider).generate(request)


def test_multiple_cases_in_a_requested_category_are_allowed() -> None:
    request = make_request(Category.FUNCTIONAL)
    suite = SuiteModel(
        source_story_id="US-001",
        test_cases=[
            make_case("TC-001", Category.FUNCTIONAL),
            make_case("TC-002", Category.FUNCTIONAL),
        ],
    )

    result = GenerationService(StubProvider(suite)).generate(request)

    assert len(result.test_cases) == 2

