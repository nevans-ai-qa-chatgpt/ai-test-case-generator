"""Validated domain models for test-case generation."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_TEST_CASES = 6
MAX_STEPS_PER_CASE = 6


class StrictModel(BaseModel):
    """Shared rules for data entering or leaving the application."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TestCategory(StrEnum):
    """The behavior class exercised by a test case."""

    FUNCTIONAL = "functional"
    NEGATIVE = "negative"
    EDGE = "edge"


class Priority(StrEnum):
    """Business-oriented execution priority."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CasePlanItem(StrictModel):
    """One human-authorized requirement/category combination."""

    id: str = Field(pattern=r"^PLAN-[0-9]{3}$")
    requirement_id: str = Field(pattern=r"^(?:AC-[0-9]{3,}|NARRATIVE)$")
    category: TestCategory


class UserStory(StrictModel):
    """A product requirement supplied to the generator."""

    id: str = Field(min_length=1, examples=["US-001"])
    title: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    acceptance_criteria: list[str] = Field(default_factory=list)


class GenerationRequest(StrictModel):
    """A user story plus the categories requested from a provider."""

    story: UserStory
    categories: list[TestCategory] = Field(
        default_factory=lambda: list(TestCategory),
        min_length=1,
    )
    case_plan: list[CasePlanItem] = Field(
        default_factory=list,
        max_length=MAX_TEST_CASES,
    )

    @model_validator(mode="after")
    def request_constraints_are_consistent(self) -> Self:
        if len(self.categories) != len(set(self.categories)):
            raise ValueError("requested categories must be unique")

        plan_ids = [item.id for item in self.case_plan]
        if len(plan_ids) != len(set(plan_ids)):
            raise ValueError("case plan IDs must be unique")

        pairs = [(item.requirement_id, item.category) for item in self.case_plan]
        if len(pairs) != len(set(pairs)):
            raise ValueError("case plan requirement/category pairs must be unique")

        unexpected_categories = {
            item.category for item in self.case_plan
        } - set(self.categories)
        if unexpected_categories:
            raise ValueError("case plan categories must be requested")

        if self.case_plan:
            requirement_ids = (
                {
                    f"AC-{index:03d}"
                    for index in range(1, len(self.story.acceptance_criteria) + 1)
                }
                if self.story.acceptance_criteria
                else {"NARRATIVE"}
            )
            planned_ids = {item.requirement_id for item in self.case_plan}
            if planned_ids - requirement_ids:
                raise ValueError("case plan contains unknown requirement IDs")
            if requirement_ids - planned_ids:
                raise ValueError("case plan must cover every authoritative requirement")
        return self


class TestStep(StrictModel):
    """One action and its observable expected result."""

    number: int = Field(ge=1)
    action: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)


class TestCase(StrictModel):
    """A test case that can be reviewed or executed by a tester."""

    id: str = Field(min_length=1, examples=["TC-001"])
    plan_id: str | None = Field(default=None, pattern=r"^PLAN-[0-9]{3}$")
    title: str = Field(min_length=1)
    category: TestCategory
    priority: Priority
    objective: str = Field(min_length=1)
    preconditions: list[str] = Field(default_factory=list)
    steps: list[TestStep] = Field(min_length=1, max_length=MAX_STEPS_PER_CASE)
    source_requirements: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def steps_are_consecutively_numbered(self) -> Self:
        actual = [step.number for step in self.steps]
        expected = list(range(1, len(self.steps) + 1))
        if actual != expected:
            raise ValueError("steps must be numbered consecutively starting at 1")
        return self


class CoverageGap(StrictModel):
    """A requested category that lacks enough source evidence for a test."""

    category: TestCategory
    reason: str = Field(min_length=1)


class TestSuite(StrictModel):
    """A versioned collection of generated test cases for one user story."""

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    source_story_id: str = Field(min_length=1)
    test_cases: list[TestCase] = Field(
        default_factory=list,
        max_length=MAX_TEST_CASES,
    )
    coverage_gaps: list[CoverageGap] = Field(default_factory=list)

    @model_validator(mode="after")
    def cases_and_gaps_are_consistent(self) -> Self:
        if not self.test_cases and not self.coverage_gaps:
            raise ValueError("a suite must contain a test case or coverage gap")

        ids = [test_case.id for test_case in self.test_cases]
        if len(ids) != len(set(ids)):
            raise ValueError("test case IDs must be unique")

        gap_categories = [gap.category for gap in self.coverage_gaps]
        if len(gap_categories) != len(set(gap_categories)):
            raise ValueError("coverage gap categories must be unique")

        case_categories = {test_case.category for test_case in self.test_cases}
        overlap = case_categories & set(gap_categories)
        if overlap:
            raise ValueError(
                "a category cannot have both test cases and a coverage gap"
            )
        return self
