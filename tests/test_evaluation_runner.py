import hashlib
import json
from pathlib import Path

import pytest

from ai_test_case_generator.evaluation import load_evaluation_dataset
from ai_test_case_generator.evaluation_runner import (
    EvaluationCaseResult,
    EvaluationRunError,
    EvaluationRunManifest,
    EvaluationRunner,
)
from ai_test_case_generator.models import GenerationRequest, TestSuite as SuiteModel
from ai_test_case_generator.providers import FakeTestCaseProvider, ProviderError
from ai_test_case_generator.providers.base import TokenUsage
from ai_test_case_generator.quality import QualityReport


DATASET_PATH = Path(__file__).parents[1] / "evals" / "dataset.json"


def make_runner(tmp_path: Path, provider=None) -> EvaluationRunner:
    return EvaluationRunner(
        dataset=load_evaluation_dataset(DATASET_PATH),
        dataset_sha256=hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest(),
        provider=provider or FakeTestCaseProvider(),
        output_dir=tmp_path / "run",
    )


class FailingOnceFakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self._failed = False
        self._delegate = FakeTestCaseProvider()

    def generate(self, request: GenerationRequest) -> SuiteModel:
        if request.story.id == "US-EVAL-002" and not self._failed:
            self._failed = True
            raise ProviderError("simulated provider failure")
        return self._delegate.generate(request)


class InterruptingFakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self._calls = 0
        self._delegate = FakeTestCaseProvider()

    def generate(self, request: GenerationRequest) -> SuiteModel:
        self._calls += 1
        if self._calls == 2:
            raise KeyboardInterrupt
        return self._delegate.generate(request)


class UsageFakeProvider(FakeTestCaseProvider):
    last_usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)


class RawContractFailureOnceProvider:
    name = "fake"

    def __init__(self) -> None:
        self._failed = False
        self._delegate = FakeTestCaseProvider()
        self.last_raw_response: str | None = None

    def generate(self, request: GenerationRequest) -> SuiteModel:
        self.last_raw_response = None
        suite = self._delegate.generate(request)
        if self._failed:
            return suite

        self._failed = True
        self.last_raw_response = '{"generated":"unsupported citation"}'
        invalid_case = suite.test_cases[0].model_copy(
            update={"source_requirements": ["An invented requirement."]}
        )
        return suite.model_copy(
            update={"test_cases": [invalid_case, *suite.test_cases[1:]]}
        )


def test_runner_writes_manifest_suite_quality_and_result(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, UsageFakeProvider())

    summary = runner.run(case_ids=["EVAL-001"])

    run_dir = tmp_path / "run"
    case_dir = run_dir / "cases" / "EVAL-001"
    manifest = EvaluationRunManifest.model_validate_json(
        (run_dir / "run.json").read_text(encoding="utf-8")
    )
    suite = SuiteModel.model_validate_json(
        (case_dir / "suite.json").read_text(encoding="utf-8")
    )
    quality_data = json.loads((case_dir / "quality.json").read_text(encoding="utf-8"))
    quality_data.pop("passed")
    quality = QualityReport.model_validate(quality_data)
    result = EvaluationCaseResult.model_validate_json(
        (case_dir / "result.json").read_text(encoding="utf-8")
    )

    assert summary.completed == 1
    assert manifest.provider == "fake"
    assert suite.source_story_id == "US-EVAL-001"
    assert quality.source_story_id == "US-EVAL-001"
    assert result.status == "completed"
    assert result.quality_findings_count == len(quality.findings)
    assert result.token_usage == TokenUsage(
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
    )


def test_runner_skips_completed_cases_when_resumed(tmp_path: Path) -> None:
    make_runner(tmp_path).run(case_ids=["EVAL-001", "EVAL-002"])

    summary = make_runner(tmp_path).run(
        case_ids=["EVAL-001", "EVAL-002", "EVAL-003"]
    )

    assert summary.completed == 1
    assert summary.skipped == 2
    assert summary.failed == 0


def test_runner_records_failure_continues_and_retries_on_resume(
    tmp_path: Path,
) -> None:
    provider = FailingOnceFakeProvider()
    runner = make_runner(tmp_path, provider)

    first_summary = runner.run(
        case_ids=["EVAL-001", "EVAL-002", "EVAL-003"]
    )
    failed_result_path = (
        tmp_path / "run" / "cases" / "EVAL-002" / "result.json"
    )
    failed_result = EvaluationCaseResult.model_validate_json(
        failed_result_path.read_text(encoding="utf-8")
    )

    second_summary = make_runner(tmp_path, provider).run(
        case_ids=["EVAL-001", "EVAL-002", "EVAL-003"]
    )
    retried_result = EvaluationCaseResult.model_validate_json(
        failed_result_path.read_text(encoding="utf-8")
    )

    assert first_summary.completed == 2
    assert first_summary.failed == 1
    assert failed_result.status == "failed"
    assert failed_result.error_type == "ProviderError"
    assert second_summary.completed == 1
    assert second_summary.skipped == 2
    assert retried_result.status == "completed"


def test_runner_preserves_failed_raw_response_and_removes_it_after_retry(
    tmp_path: Path,
) -> None:
    provider = RawContractFailureOnceProvider()
    runner = make_runner(tmp_path, provider)
    case_dir = tmp_path / "run" / "cases" / "EVAL-001"
    raw_response_path = case_dir / "raw_response.txt"

    first_summary = runner.run(case_ids=["EVAL-001"])
    failed_result = EvaluationCaseResult.model_validate_json(
        (case_dir / "result.json").read_text(encoding="utf-8")
    )

    assert first_summary.failed == 1
    assert failed_result.error_type == "ProviderContractError"
    assert raw_response_path.read_text(encoding="utf-8") == (
        '{"generated":"unsupported citation"}'
    )

    second_summary = runner.run(case_ids=["EVAL-001"])

    assert second_summary.completed == 1
    assert not raw_response_path.exists()


def test_runner_preserves_progress_across_keyboard_interrupt(
    tmp_path: Path,
) -> None:
    with pytest.raises(KeyboardInterrupt):
        make_runner(tmp_path, InterruptingFakeProvider()).run(
            case_ids=["EVAL-001", "EVAL-002", "EVAL-003"]
        )

    first_result = tmp_path / "run" / "cases" / "EVAL-001" / "result.json"
    interrupted_result = tmp_path / "run" / "cases" / "EVAL-002" / "result.json"
    assert first_result.exists()
    assert not interrupted_result.exists()

    summary = make_runner(tmp_path).run(
        case_ids=["EVAL-001", "EVAL-002", "EVAL-003"]
    )

    assert summary.completed == 2
    assert summary.skipped == 1


def test_runner_rejects_a_different_configuration_in_the_same_directory(
    tmp_path: Path,
) -> None:
    make_runner(tmp_path).run(case_ids=["EVAL-001"])
    changed_runner = EvaluationRunner(
        dataset=load_evaluation_dataset(DATASET_PATH),
        dataset_sha256="0" * 64,
        provider=FakeTestCaseProvider(),
        output_dir=tmp_path / "run",
    )

    with pytest.raises(EvaluationRunError, match="configuration differs"):
        changed_runner.run(case_ids=["EVAL-002"])


def test_runner_rejects_unknown_or_duplicate_case_ids(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)

    with pytest.raises(EvaluationRunError, match="unknown"):
        runner.run(case_ids=["EVAL-999"])
    with pytest.raises(EvaluationRunError, match="must be unique"):
        runner.run(case_ids=["EVAL-001", "EVAL-001"])


def test_completed_result_json_is_machine_readable(tmp_path: Path) -> None:
    make_runner(tmp_path).run(case_ids=["EVAL-008"])
    result_path = tmp_path / "run" / "cases" / "EVAL-008" / "result.json"

    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert result["evaluation_id"] == "EVAL-008"
    assert result["status"] == "completed"
    assert result["duration_seconds"] >= 0


def test_recorded_qwen_canary_matches_the_run_contract() -> None:
    run_dir = (
        Path(__file__).parents[1]
        / "evals"
        / "runs"
        / "qwen3-4b-prompt-v1.2"
    )

    manifest = EvaluationRunManifest.model_validate_json(
        (run_dir / "run.json").read_text(encoding="utf-8")
    )
    result = EvaluationCaseResult.model_validate_json(
        (run_dir / "cases" / "EVAL-001" / "result.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest.provider == "ollama"
    assert manifest.model == "qwen3:4b-instruct"
    assert manifest.prompt_version == "1.2"
    assert result.status == "failed"
    assert result.error_type == "ProviderError"
    assert result.duration_seconds >= 600


def test_recorded_bounded_qwen_canary_matches_the_run_contract() -> None:
    run_dir = (
        Path(__file__).parents[1]
        / "evals"
        / "runs"
        / "qwen3-4b-prompt-v1.3"
    )

    manifest = EvaluationRunManifest.model_validate_json(
        (run_dir / "run.json").read_text(encoding="utf-8")
    )
    result = EvaluationCaseResult.model_validate_json(
        (run_dir / "cases" / "EVAL-001" / "result.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest.provider == "ollama"
    assert manifest.model == "qwen3:4b-instruct"
    assert manifest.prompt_version == "1.3"
    assert manifest.provider_parameters["timeout_seconds"] == 600.0
    assert result.status == "failed"
    assert result.error_type == "ProviderError"
    assert "test_cases.0 (value_error)" in result.error_message
    assert 200 <= result.duration_seconds < 600


def test_recorded_auto_numbered_qwen_canary_matches_the_run_contract() -> None:
    run_dir = (
        Path(__file__).parents[1]
        / "evals"
        / "runs"
        / "qwen3-4b-prompt-v1.4"
    )

    manifest = EvaluationRunManifest.model_validate_json(
        (run_dir / "run.json").read_text(encoding="utf-8")
    )
    result = EvaluationCaseResult.model_validate_json(
        (run_dir / "cases" / "EVAL-001" / "result.json").read_text(
            encoding="utf-8"
        )
    )
    suite = SuiteModel.model_validate_json(
        (run_dir / "cases" / "EVAL-001" / "suite.json").read_text(
            encoding="utf-8"
        )
    )
    quality_data = json.loads(
        (run_dir / "cases" / "EVAL-001" / "quality.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest.provider == "ollama"
    assert manifest.model == "qwen3:4b-instruct"
    assert manifest.prompt_version == "1.4"
    assert result.status == "completed"
    assert result.token_usage is not None
    assert result.token_usage.total_tokens == 2541
    assert result.quality_findings_count == len(quality_data["findings"]) == 10
    assert len(suite.test_cases) == 6
    assert all(
        [step.number for step in case.steps] == list(range(1, len(case.steps) + 1))
        for case in suite.test_cases
    )


def test_recorded_grounded_qwen_canary_matches_the_run_contract() -> None:
    run_dir = (
        Path(__file__).parents[1]
        / "evals"
        / "runs"
        / "qwen3-4b-prompt-v1.5"
    )

    manifest = EvaluationRunManifest.model_validate_json(
        (run_dir / "run.json").read_text(encoding="utf-8")
    )
    result = EvaluationCaseResult.model_validate_json(
        (run_dir / "cases" / "EVAL-001" / "result.json").read_text(
            encoding="utf-8"
        )
    )
    suite = SuiteModel.model_validate_json(
        (run_dir / "cases" / "EVAL-001" / "suite.json").read_text(
            encoding="utf-8"
        )
    )
    quality_data = json.loads(
        (run_dir / "cases" / "EVAL-001" / "quality.json").read_text(
            encoding="utf-8"
        )
    )
    authoritative = {
        "A registered user receives a reset link that is valid for 30 minutes.",
        "An unregistered email address receives the same visible confirmation, but no reset email is sent.",
        "A reset link can be used only once.",
        "The new password must satisfy the configured password policy.",
    }
    cited = {
        requirement
        for case in suite.test_cases
        for requirement in case.source_requirements
    }

    assert manifest.prompt_version == "1.5"
    assert result.status == "completed"
    assert result.token_usage is not None
    assert result.token_usage.total_tokens == 2850
    assert result.quality_findings_count == len(quality_data["findings"]) == 9
    assert all(case.preconditions for case in suite.test_cases)
    assert cited == authoritative


def test_recorded_grounded_gemma_canary_preserves_contract_failure() -> None:
    run_dir = (
        Path(__file__).parents[1]
        / "evals"
        / "runs"
        / "gemma3-12b-prompt-v1.5"
    )

    manifest = EvaluationRunManifest.model_validate_json(
        (run_dir / "run.json").read_text(encoding="utf-8")
    )
    case_dir = run_dir / "cases" / "EVAL-001"
    result = EvaluationCaseResult.model_validate_json(
        (case_dir / "result.json").read_text(encoding="utf-8")
    )

    assert manifest.provider == "ollama"
    assert manifest.model == "gemma3:12b"
    assert manifest.prompt_version == "1.5"
    assert manifest.provider_parameters["temperature"] == 0
    assert manifest.provider_parameters["timeout_seconds"] == 900.0
    assert result.status == "failed"
    assert result.error_type == "ProviderContractError"
    assert result.error_message == "TC-006 cites unsupported source requirements"
    assert result.duration_seconds > 600
    assert result.token_usage is None
    assert result.quality_findings_count is None
    assert not (case_dir / "suite.json").exists()
    assert not (case_dir / "quality.json").exists()
