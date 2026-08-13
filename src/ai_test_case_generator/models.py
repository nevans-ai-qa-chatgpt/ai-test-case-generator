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

    @model_validator(mode="after")
    def categories_are_unique(self) -> Self:
        if len(self.categories) != len(set(self.categories)):
            raise ValueError("requested categories must be unique")
        return self


class TestStep(StrictModel):
    """One action and its observable expected result."""

    number: int = Field(ge=1)
    action: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)


class TestCase(StrictModel):
    """A test case that can be reviewed or executed by a tester."""

    id: str = Field(min_length=1, examples=["TC-001"])
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


class TestSuite(StrictModel):
    """A versioned collection of generated test cases for one user story."""

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    source_story_id: str = Field(min_length=1)
    test_cases: list[TestCase] = Field(min_length=1, max_length=MAX_TEST_CASES)

    @model_validator(mode="after")
    def test_case_ids_are_unique(self) -> Self:
        ids = [test_case.id for test_case in self.test_cases]
        if len(ids) != len(set(ids)):
            raise ValueError("test case IDs must be unique")
        return self
