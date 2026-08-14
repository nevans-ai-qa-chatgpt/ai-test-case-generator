"""Model-facing output contract and deterministic domain conversion."""

from typing import Self

from pydantic import Field, model_validator

from ai_test_case_generator.models import (
    CasePlanItem,
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


class ModelTestStep(StrictModel):
    """One model-generated step, ordered by its position in the list."""

    action: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)


class ModelTestCase(StrictModel):
    """A generated case before deterministic step numbering."""

    id: str = Field(min_length=1, examples=["TC-001"])
    plan_id: str = Field(pattern=r"^PLAN-[0-9]{3}$")
    title: str = Field(min_length=1)
    priority: Priority
    objective: str = Field(min_length=1)
    preconditions: list[str] = Field(min_length=1)
    steps: list[ModelTestStep] = Field(
        min_length=1,
        max_length=MAX_STEPS_PER_CASE,
    )
    tags: list[str] = Field(default_factory=list)

    def to_test_case(
        self,
        plan_item: CasePlanItem,
        requirement: str,
    ) -> TestCase:
        """Assign consecutive numbers from the model's list order."""

        case_data = self.model_dump(exclude={"steps", "plan_id"})
        return TestCase(
            **case_data,
            plan_id=plan_item.id,
            category=plan_item.category,
            steps=[
                TestStep(number=number, **step.model_dump())
                for number, step in enumerate(self.steps, start=1)
            ],
            source_requirements=[requirement],
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

        plan_ids = [test_case.plan_id for test_case in self.test_cases]
        if len(plan_ids) != len(set(plan_ids)):
            raise ValueError("model test-case plan IDs must be unique")
        return self

    def to_test_suite(self, request: GenerationRequest) -> TestSuite:
        """Build the public suite after applying deterministic fields."""

        if not request.case_plan:
            raise ValueError("model-backed generation requires a case plan")
        requirements = requirement_text_by_id(request)
        plan_by_id = {item.id: item for item in request.case_plan}
        returned_plan_ids = {test_case.plan_id for test_case in self.test_cases}
        if returned_plan_ids != set(plan_by_id):
            raise ValueError("model output does not match the authorized case plan")

        planned_categories = {item.category for item in request.case_plan}
        expected_gap_categories = set(request.categories) - planned_categories
        returned_gap_categories = {gap.category for gap in self.coverage_gaps}
        if returned_gap_categories != expected_gap_categories:
            raise ValueError("model output does not match the required coverage gaps")

        return TestSuite(
            schema_version=self.schema_version,
            source_story_id=self.source_story_id,
            test_cases=[
                test_case.to_test_case(
                    plan_by_id[test_case.plan_id],
                    requirements[plan_by_id[test_case.plan_id].requirement_id],
                )
                for test_case in self.test_cases
            ],
            coverage_gaps=[
                CoverageGap.model_validate(gap.model_dump())
                for gap in self.coverage_gaps
            ],
        )


def model_output_json_schema(request: GenerationRequest) -> dict[str, object]:
    """Build the schema with an exact enum of IDs valid for this request."""

    if not request.case_plan:
        raise ValueError("model-backed generation requires a case plan")
    schema = ModelTestSuite.model_json_schema()
    case_properties = schema["$defs"]["ModelTestCase"]["properties"]
    plan_id = case_properties["plan_id"]
    plan_id.clear()
    plan_id.update(
        type="string",
        enum=[item.id for item in request.case_plan],
    )
    test_cases = schema["properties"]["test_cases"]
    test_cases["minItems"] = len(request.case_plan)
    test_cases["maxItems"] = len(request.case_plan)

    planned_categories = {item.category for item in request.case_plan}
    gap_categories = [
        category
        for category in request.categories
        if category not in planned_categories
    ]
    coverage_gaps = schema["properties"]["coverage_gaps"]
    coverage_gaps["minItems"] = len(gap_categories)
    coverage_gaps["maxItems"] = len(gap_categories)
    if gap_categories:
        schema["$defs"]["TestCategory"]["enum"] = [
            category.value for category in gap_categories
        ]
    return schema
