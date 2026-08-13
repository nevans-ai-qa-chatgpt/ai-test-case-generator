"""Models and loading helpers for representative generation evaluations."""

import json
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator

from ai_test_case_generator.models import GenerationRequest, StrictModel


class EvaluationCase(StrictModel):
    """One model input plus an independent human-review rubric."""

    id: str = Field(min_length=1, pattern=r"^EVAL-[0-9]{3}$")
    purpose: str = Field(min_length=1)
    request: GenerationRequest
    review_assertions: list[str] = Field(min_length=1)
    forbidden_assumptions: list[str] = Field(min_length=1)
    tags: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def review_metadata_is_unique(self) -> Self:
        for field_name in (
            "review_assertions",
            "forbidden_assumptions",
            "tags",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must contain unique values")
        return self


class EvaluationDataset(StrictModel):
    """A versioned collection of representative generation evaluations."""

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    cases: list[EvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> Self:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation case IDs must be unique")

        story_ids = [case.request.story.id for case in self.cases]
        if len(story_ids) != len(set(story_ids)):
            raise ValueError("evaluation story IDs must be unique")
        return self


def load_evaluation_dataset(path: Path) -> EvaluationDataset:
    """Read and validate an evaluation dataset from JSON."""

    data = json.loads(path.read_text(encoding="utf-8"))
    return EvaluationDataset.model_validate(data)
