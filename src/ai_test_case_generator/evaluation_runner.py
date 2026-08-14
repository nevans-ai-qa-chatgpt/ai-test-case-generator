"""Sequential, resumable execution for representative evaluation datasets."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal, Self

from pydantic import Field, model_validator

from ai_test_case_generator.evaluation import EvaluationCase, EvaluationDataset
from ai_test_case_generator.models import StrictModel, TestSuite
from ai_test_case_generator.providers import ProviderError, TestCaseProvider
from ai_test_case_generator.providers.base import TokenUsage
from ai_test_case_generator.quality import QualityReport, evaluate_quality
from ai_test_case_generator.service import GenerationService, ProviderContractError


class EvaluationRunError(ValueError):
    """Raised when an evaluation run cannot be created or resumed safely."""


class EvaluationRunManifest(StrictModel):
    """Immutable configuration shared by every result in one run directory."""

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    created_at: datetime
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=1)
    model: str | None = None
    prompt_version: str | None = None
    provider_parameters: dict[str, str | int | float | bool] = Field(
        default_factory=dict
    )


class EvaluationCaseResult(StrictModel):
    """The authoritative completion or failure marker for one case."""

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    evaluation_id: str = Field(pattern=r"^EVAL-[0-9]{3}$")
    source_story_id: str = Field(min_length=1)
    status: Literal["completed", "failed"]
    started_at: datetime
    finished_at: datetime
    duration_seconds: float = Field(ge=0)
    token_usage: TokenUsage | None = None
    quality_findings_count: int | None = Field(default=None, ge=0)
    error_type: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def status_fields_are_consistent(self) -> Self:
        if self.status == "completed":
            if self.quality_findings_count is None:
                raise ValueError("completed results require a quality finding count")
            if self.error_type is not None or self.error_message is not None:
                raise ValueError("completed results cannot contain an error")
        elif not self.error_type or not self.error_message:
            raise ValueError("failed results require an error type and message")
        return self


@dataclass(frozen=True)
class EvaluationRunSummary:
    """Counts produced by one invocation of a possibly resumed run."""

    completed: int = 0
    skipped: int = 0
    failed: int = 0


class EvaluationRunner:
    """Run selected cases sequentially and save progress after every case."""

    def __init__(
        self,
        *,
        dataset: EvaluationDataset,
        dataset_sha256: str,
        provider: TestCaseProvider,
        output_dir: Path,
        provider_parameters: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        self._dataset = dataset
        self._provider = provider
        self._service = GenerationService(provider)
        self._output_dir = output_dir
        self._manifest = EvaluationRunManifest(
            created_at=datetime.now(UTC),
            dataset_sha256=dataset_sha256,
            provider=provider.name,
            model=getattr(provider, "model", None),
            prompt_version=getattr(provider, "prompt_version", None),
            provider_parameters=provider_parameters or {},
        )

    def run(
        self,
        *,
        case_ids: list[str] | None = None,
        force: bool = False,
    ) -> EvaluationRunSummary:
        """Run cases in dataset order, retrying failures and skipping successes."""

        cases = self._select_cases(case_ids)
        self._prepare_run_directory()
        completed = 0
        skipped = 0
        failed = 0

        for evaluation_case in cases:
            if not force and self._case_is_complete(evaluation_case):
                skipped += 1
                print(f"[{evaluation_case.id}] skipped (already completed)")
                continue

            print(f"[{evaluation_case.id}] running")
            if self._run_case(evaluation_case):
                completed += 1
            else:
                failed += 1

        return EvaluationRunSummary(
            completed=completed,
            skipped=skipped,
            failed=failed,
        )

    def _select_cases(self, case_ids: list[str] | None) -> list[EvaluationCase]:
        if not case_ids:
            return self._dataset.cases

        requested = set(case_ids)
        if len(requested) != len(case_ids):
            raise EvaluationRunError("selected evaluation case IDs must be unique")
        known = {case.id for case in self._dataset.cases}
        unknown = sorted(requested - known)
        if unknown:
            raise EvaluationRunError(
                "unknown evaluation case ID(s): " + ", ".join(unknown)
            )
        return [case for case in self._dataset.cases if case.id in requested]

    def _prepare_run_directory(self) -> None:
        manifest_path = self._output_dir / "run.json"
        if manifest_path.exists():
            saved = EvaluationRunManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
            expected_config = self._manifest.model_dump(exclude={"created_at"})
            saved_config = saved.model_dump(exclude={"created_at"})
            if saved_config != expected_config:
                raise EvaluationRunError(
                    "run configuration differs from the existing run.json; "
                    "use a different output directory"
                )
            return

        if self._output_dir.exists() and any(self._output_dir.iterdir()):
            raise EvaluationRunError(
                "output directory is not empty and has no run.json manifest"
            )
        self._output_dir.mkdir(parents=True, exist_ok=True)
        _write_model_atomic(manifest_path, self._manifest)

    def _case_is_complete(self, evaluation_case: EvaluationCase) -> bool:
        case_dir = self._case_dir(evaluation_case)
        result_path = case_dir / "result.json"
        if not result_path.exists():
            return False

        result = EvaluationCaseResult.model_validate_json(
            result_path.read_text(encoding="utf-8")
        )
        if result.status == "failed":
            return False
        if (
            result.evaluation_id != evaluation_case.id
            or result.source_story_id != evaluation_case.request.story.id
        ):
            raise EvaluationRunError(
                f"{evaluation_case.id} result does not match the dataset case"
            )

        suite_path = case_dir / "suite.json"
        quality_path = case_dir / "quality.json"
        if not suite_path.exists() or not quality_path.exists():
            raise EvaluationRunError(
                f"{evaluation_case.id} is marked complete but an artifact is missing"
            )
        suite = TestSuite.model_validate_json(suite_path.read_text(encoding="utf-8"))
        quality = _load_quality_artifact(quality_path)
        if (
            suite.source_story_id != evaluation_case.request.story.id
            or quality.source_story_id != evaluation_case.request.story.id
        ):
            raise EvaluationRunError(
                f"{evaluation_case.id} artifacts do not match the dataset story"
            )
        if result.quality_findings_count != len(quality.findings):
            raise EvaluationRunError(
                f"{evaluation_case.id} result does not match its quality report"
            )
        return True

    def _run_case(self, evaluation_case: EvaluationCase) -> bool:
        case_dir = self._case_dir(evaluation_case)
        case_dir.mkdir(parents=True, exist_ok=True)
        raw_response_path = case_dir / "raw_response.txt"
        started_at = datetime.now(UTC)
        started_timer = perf_counter()

        try:
            suite = self._service.generate(evaluation_case.request)
            quality = evaluate_quality(evaluation_case.request, suite)
        except (ProviderError, ProviderContractError) as error:
            raw_response = getattr(self._provider, "last_raw_response", None)
            if isinstance(raw_response, str) and raw_response:
                _write_text_atomic(raw_response_path, raw_response)
            else:
                raw_response_path.unlink(missing_ok=True)
            result = EvaluationCaseResult(
                evaluation_id=evaluation_case.id,
                source_story_id=evaluation_case.request.story.id,
                status="failed",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                duration_seconds=perf_counter() - started_timer,
                error_type=type(error).__name__,
                error_message=str(error) or "No error message was provided.",
            )
            _write_model_atomic(case_dir / "result.json", result)
            print(f"[{evaluation_case.id}] failed: {error}")
            return False

        duration = perf_counter() - started_timer
        usage = getattr(self._provider, "last_usage", None)
        result = EvaluationCaseResult(
            evaluation_id=evaluation_case.id,
            source_story_id=evaluation_case.request.story.id,
            status="completed",
            started_at=started_at,
            finished_at=datetime.now(UTC),
            duration_seconds=duration,
            token_usage=usage,
            quality_findings_count=len(quality.findings),
        )
        _write_model_atomic(case_dir / "suite.json", suite)
        _write_model_atomic(case_dir / "quality.json", quality)
        _write_model_atomic(case_dir / "result.json", result)
        raw_response_path.unlink(missing_ok=True)
        print(
            f"[{evaluation_case.id}] completed in {duration:.1f}s "
            f"({len(quality.findings)} quality finding(s))"
        )
        return True

    def _case_dir(self, evaluation_case: EvaluationCase) -> Path:
        return self._output_dir / "cases" / evaluation_case.id


def _write_model_atomic(path: Path, model: StrictModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    output = json.dumps(
        model.model_dump(mode="json"),
        indent=2,
        ensure_ascii=False,
    ) + "\n"
    temporary_path.write_text(output, encoding="utf-8")
    temporary_path.replace(path)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


def _load_quality_artifact(path: Path) -> QualityReport:
    data = json.loads(path.read_text(encoding="utf-8"))
    reported_passed = data.pop("passed", None)
    quality = QualityReport.model_validate(data)
    if reported_passed is not None and reported_passed != quality.passed:
        raise EvaluationRunError(
            f"quality artifact has an inconsistent passed value: {path}"
        )
    return quality
