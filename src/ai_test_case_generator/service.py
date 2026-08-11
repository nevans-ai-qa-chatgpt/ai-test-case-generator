"""Application service for guarded test-case generation."""

from ai_test_case_generator.models import GenerationRequest, TestSuite
from ai_test_case_generator.providers import TestCaseProvider


class ProviderContractError(ValueError):
    """Raised when structurally valid provider output violates the request."""


class GenerationService:
    """Generate a suite and enforce semantic rules at the provider boundary."""

    def __init__(self, provider: TestCaseProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        """Expose the active provider without leaking its implementation."""
        return self._provider.name

    def generate(self, request: GenerationRequest) -> TestSuite:
        """Return a suite only when it fulfills the generation request."""
        suite = self._provider.generate(request)
        self._validate_source_story(request, suite)
        self._validate_categories(request, suite)
        return suite

    @staticmethod
    def _validate_source_story(
        request: GenerationRequest,
        suite: TestSuite,
    ) -> None:
        if suite.source_story_id != request.story.id:
            raise ProviderContractError(
                "provider returned source story "
                f"{suite.source_story_id!r}; expected {request.story.id!r}"
            )

    @staticmethod
    def _validate_categories(
        request: GenerationRequest,
        suite: TestSuite,
    ) -> None:
        requested = set(request.categories)
        returned = {test_case.category for test_case in suite.test_cases}
        missing = requested - returned
        unexpected = returned - requested

        problems: list[str] = []
        if missing:
            problems.append(f"missing categories: {_category_names(missing)}")
        if unexpected:
            problems.append(f"unexpected categories: {_category_names(unexpected)}")
        if problems:
            raise ProviderContractError("; ".join(problems))


def _category_names(categories: set[object]) -> str:
    return ", ".join(sorted(str(category) for category in categories))

