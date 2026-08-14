"""A deterministic provider for development and automated tests."""

from collections.abc import Callable

from ai_test_case_generator.models import (
    CoverageGap,
    GenerationRequest,
    Priority,
    TestCase,
    TestCategory,
    TestStep,
    TestSuite,
    UserStory,
)
from ai_test_case_generator.requirements import requirement_text_by_id

CaseFactory = Callable[[str, UserStory, list[str]], TestCase]


class FakeTestCaseProvider:
    """Generate predictable examples without pretending to reason like an AI."""

    name = "fake"

    def generate(self, request: GenerationRequest) -> TestSuite:
        requirements = request.story.acceptance_criteria or [request.story.narrative]
        factories: dict[TestCategory, CaseFactory] = {
            TestCategory.FUNCTIONAL: self._functional_case,
            TestCategory.NEGATIVE: self._negative_case,
            TestCategory.EDGE: self._edge_case,
        }
        if not request.case_plan:
            cases = [
                factories[category](
                    f"TC-{index:03d}",
                    request.story,
                    requirements,
                )
                for index, category in enumerate(request.categories, start=1)
            ]
            return TestSuite(source_story_id=request.story.id, test_cases=cases)

        requirements_by_id = requirement_text_by_id(request)
        cases = [
            factories[plan_item.category](
                f"TC-{index:03d}",
                request.story,
                [requirements_by_id[plan_item.requirement_id]],
            ).model_copy(update={"plan_id": plan_item.id})
            for index, plan_item in enumerate(request.case_plan, start=1)
        ]
        planned_categories = {item.category for item in request.case_plan}
        gaps = [
            CoverageGap(
                category=category,
                reason="The authorized case plan contains no supported scenario.",
            )
            for category in request.categories
            if category not in planned_categories
        ]
        return TestSuite(
            source_story_id=request.story.id,
            test_cases=cases,
            coverage_gaps=gaps,
        )

    @staticmethod
    def _functional_case(
        case_id: str,
        story: UserStory,
        requirements: list[str],
    ) -> TestCase:
        return TestCase(
            id=case_id,
            title=f"{story.title} — expected workflow",
            category=TestCategory.FUNCTIONAL,
            priority=Priority.HIGH,
            objective="Verify the primary user workflow succeeds.",
            preconditions=["The system is available for testing."],
            steps=[
                TestStep(
                    number=1,
                    action=f"Perform the expected workflow for: {story.title}.",
                    expected_result="The requested outcome is completed successfully.",
                )
            ],
            source_requirements=requirements,
            tags=["fake-provider", "functional"],
        )

    @staticmethod
    def _negative_case(
        case_id: str,
        story: UserStory,
        requirements: list[str],
    ) -> TestCase:
        return TestCase(
            id=case_id,
            title=f"{story.title} — invalid input",
            category=TestCategory.NEGATIVE,
            priority=Priority.MEDIUM,
            objective="Verify invalid input is rejected safely.",
            preconditions=["The system is available for testing."],
            steps=[
                TestStep(
                    number=1,
                    action=f"Attempt {story.title} with invalid input.",
                    expected_result="The request is rejected with a useful error message.",
                )
            ],
            source_requirements=requirements,
            tags=["fake-provider", "negative"],
        )

    @staticmethod
    def _edge_case(
        case_id: str,
        story: UserStory,
        requirements: list[str],
    ) -> TestCase:
        return TestCase(
            id=case_id,
            title=f"{story.title} — boundary condition",
            category=TestCategory.EDGE,
            priority=Priority.MEDIUM,
            objective="Verify a boundary condition is handled consistently.",
            preconditions=["The system is available for testing."],
            steps=[
                TestStep(
                    number=1,
                    action=f"Perform {story.title} using a boundary value.",
                    expected_result="The boundary value is handled without an unexpected failure.",
                )
            ],
            source_requirements=requirements,
            tags=["fake-provider", "edge"],
        )
