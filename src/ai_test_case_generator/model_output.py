"""Model-facing output contract and deterministic domain conversion."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from ai_test_case_generator.models import (
    CoverageGap,
    GenerationRequest,
    MAX_STEPS_PER_CASE,
    MAX_TEST_CASES,
    Priority,
    StrictModel,
    TestCase,
    TestCategory,
    TestStep,
    TestSuite,
)
from ai_test_case_generator.requirements import requirement_text_by_id

RequirementId = Annotated[
    str,
    Field(pattern=r"^(?:AC-[0-9]{3,}|NARRATIVE)$"),
]


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
    source_requirement_ids: list[RequirementId] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)

    def to_test_case(self, requirements: dict[str, str]) -> TestCase:
        """Assign consecutive numbers from the model's list order."""

        unknown = set(self.source_requirement_ids) - requirements.keys()
        if unknown:
            raise ValueError("model output contains unknown requirement IDs")
        case_data = self.model_dump(exclude={"steps", "source_requirement_ids"})
        return TestCase(
            **case_data,
            steps=[
                TestStep(number=number, **step.model_dump())
                for number, step in enumerate(self.steps, start=1)
            ],
            source_requirements=[
                requirements[requirement_id]
                for requirement_id in self.source_requirement_ids
            ],
        )


class ModelCoverageGap(StrictModel):
    """A safe abstention when request text does not support a category."""

    category: TestCategory
    reason: str = Field(min_length=1)


class ModelTestSuite(StrictModel):
    """Structured model output that converts into the public domain contract."""

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    source_story_id: str = Field(min_length=1)
    test_cases: list[ModelTestCase] = Field(
        default_factory=list,
        max_length=MAX_TEST_CASES,
    )
    coverage_gaps: list[ModelCoverageGap] = Field(default_factory=list)

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
        if case_categories & set(gap_categories):
            raise ValueError(
                "a category cannot have both test cases and a coverage gap"
            )
        return self

    def to_test_suite(self, request: GenerationRequest) -> TestSuite:
        """Build the public suite after applying deterministic fields."""

        requirements = requirement_text_by_id(request)
        return TestSuite(
            schema_version=self.schema_version,
            source_story_id=self.source_story_id,
            test_cases=[
                test_case.to_test_case(requirements)
                for test_case in self.test_cases
            ],
            coverage_gaps=[
                CoverageGap.model_validate(gap.model_dump())
                for gap in self.coverage_gaps
            ],
        )


def model_output_json_schema(request: GenerationRequest) -> dict[str, object]:
    """Build the schema with an exact enum of IDs valid for this request."""

    schema = ModelTestSuite.model_json_schema()
    case_properties = schema["$defs"]["ModelTestCase"]["properties"]
    id_items = case_properties["source_requirement_ids"]["items"]
    id_items.clear()
    id_items.update(
        type="string",
        enum=list(requirement_text_by_id(request)),
    )
    schema["$defs"]["TestCategory"]["enum"] = [
        category.value for category in request.categories
    ]
    return schema
