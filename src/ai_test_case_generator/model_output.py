"""Model-facing output contract and deterministic domain conversion."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from ai_test_case_generator.models import (
    MAX_STEPS_PER_CASE,
    MAX_TEST_CASES,
    Priority,
    StrictModel,
    TestCase,
    TestCategory,
    TestStep,
    TestSuite,
)

SourceRequirement = Annotated[str, Field(min_length=1)]


class ModelTestStep(StrictModel):
    """One model-generated step, ordered by its position in the list."""

    action: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)


class ModelTestCase(StrictModel):
    """A generated case before deterministic step numbering."""

    id: str = Field(min_length=1, examples=["TC-001"])
    title: str = Field(min_length=1)
    category: TestCategory
    priority: Priority
    objective: str = Field(min_length=1)
    preconditions: list[str] = Field(min_length=1)
    steps: list[ModelTestStep] = Field(
        min_length=1,
        max_length=MAX_STEPS_PER_CASE,
    )
    source_requirements: list[SourceRequirement] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)

    def to_test_case(self) -> TestCase:
        """Assign consecutive numbers from the model's list order."""

        case_data = self.model_dump(exclude={"steps"})
        return TestCase(
            **case_data,
            steps=[
                TestStep(number=number, **step.model_dump())
                for number, step in enumerate(self.steps, start=1)
            ],
        )


class ModelTestSuite(StrictModel):
    """Structured model output that converts into the public domain contract."""

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    source_story_id: str = Field(min_length=1)
    test_cases: list[ModelTestCase] = Field(
        min_length=1,
        max_length=MAX_TEST_CASES,
    )

    @model_validator(mode="after")
    def test_case_ids_are_unique(self) -> Self:
        ids = [test_case.id for test_case in self.test_cases]
        if len(ids) != len(set(ids)):
            raise ValueError("test case IDs must be unique")
        return self

    def to_test_suite(self) -> TestSuite:
        """Build the public suite after applying deterministic fields."""

        return TestSuite(
            schema_version=self.schema_version,
            source_story_id=self.source_story_id,
            test_cases=[test_case.to_test_case() for test_case in self.test_cases],
        )
