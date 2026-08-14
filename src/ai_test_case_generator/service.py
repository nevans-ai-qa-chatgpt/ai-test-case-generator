"""Application service for guarded test-case generation."""

from ai_test_case_generator.models import GenerationRequest, TestSuite
from ai_test_case_generator.providers import TestCaseProvider
from ai_test_case_generator.requirements import requirement_text_by_id


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
        self._validate_case_plan(request, suite)
        self._validate_categories(request, suite)
        self._validate_traceability(request, suite)
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
    def _validate_case_plan(
        request: GenerationRequest,
        suite: TestSuite,
    ) -> None:
        if not request.case_plan:
            return

        expected = {item.id: item for item in request.case_plan}
        actual_ids = [test_case.plan_id for test_case in suite.test_cases]
        problems: list[str] = []
        if any(plan_id is None for plan_id in actual_ids):
            problems.append("generated cases must include authorized plan IDs")

        actual_non_null = [
            plan_id for plan_id in actual_ids if plan_id is not None
        ]
        if len(actual_non_null) != len(set(actual_non_null)):
            problems.append("generated case plan IDs must be unique")

        actual_by_id = {
            test_case.plan_id: test_case
            for test_case in suite.test_cases
            if test_case.plan_id is not None
        }
        missing = set(expected) - set(actual_by_id)
        unexpected = set(actual_by_id) - set(expected)
        if missing:
            problems.append("missing authorized case plan items")
        if unexpected:
            problems.append("generated cases use unauthorized plan IDs")

        requirements = requirement_text_by_id(request)
        for plan_id in set(expected) & set(actual_by_id):
            plan_item = expected[plan_id]
            test_case = actual_by_id[plan_id]
            if test_case.category is not plan_item.category:
                problems.append(f"{plan_id} uses the wrong category")
            expected_sources = [requirements[plan_item.requirement_id]]
            if test_case.source_requirements != expected_sources:
                problems.append(f"{plan_id} uses the wrong source requirement")

        planned_categories = {item.category for item in request.case_plan}
        expected_gaps = set(request.categories) - planned_categories
        actual_gaps = {gap.category for gap in suite.coverage_gaps}
        if actual_gaps != expected_gaps:
            problems.append("coverage gaps do not match the authorized case plan")

        if problems:
            raise ProviderContractError("; ".join(problems))

    @staticmethod
    def _validate_categories(
        request: GenerationRequest,
        suite: TestSuite,
    ) -> None:
        requested = set(request.categories)
        case_categories = {test_case.category for test_case in suite.test_cases}
        gap_categories = {gap.category for gap in suite.coverage_gaps}
        returned = case_categories | gap_categories
        missing = requested - returned
        unexpected = returned - requested

        problems: list[str] = []
        if missing:
            problems.append(f"missing categories: {_category_names(missing)}")
        if unexpected:
            problems.append(f"unexpected categories: {_category_names(unexpected)}")
        if problems:
            raise ProviderContractError("; ".join(problems))

    @staticmethod
    def _validate_traceability(
        request: GenerationRequest,
        suite: TestSuite,
    ) -> None:
        authoritative = set(
            request.story.acceptance_criteria or [request.story.narrative]
        )
        cited: set[str] = set()
        problems: list[str] = []

        for test_case in suite.test_cases:
            if not test_case.source_requirements:
                problems.append(f"{test_case.id} has no source requirements")
                continue
            unsupported = set(test_case.source_requirements) - authoritative
            if unsupported:
                problems.append(
                    f"{test_case.id} cites unsupported source requirements"
                )
            cited.update(set(test_case.source_requirements) & authoritative)

        missing = authoritative - cited
        if suite.test_cases and missing:
            problems.append(
                f"{len(missing)} authoritative requirement(s) are not cited"
            )
        if problems:
            raise ProviderContractError("; ".join(problems))


def _category_names(categories: set[object]) -> str:
    return ", ".join(sorted(str(category) for category in categories))
