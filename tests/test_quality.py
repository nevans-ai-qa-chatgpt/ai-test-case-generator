import json
from pathlib import Path

from ai_test_case_generator.models import GenerationRequest, TestSuite as SuiteModel
from ai_test_case_generator.quality import evaluate_quality

ROOT = Path(__file__).parents[1]
REQUEST = GenerationRequest.model_validate_json(
    (ROOT / "examples" / "password_reset_request.json").read_text(encoding="utf-8")
)


def load_suite(relative_path: str) -> SuiteModel:
    return SuiteModel.model_validate_json(
        (ROOT / relative_path).read_text(encoding="utf-8")
    )


def finding_ids(relative_path: str) -> set[tuple[str, str]]:
    report = evaluate_quality(REQUEST, load_suite(relative_path))
    return {(finding.test_case_id, finding.rule_id) for finding in report.findings}


def test_baseline_flags_the_measured_security_and_grounding_defects() -> None:
    findings = finding_ids("evals/baselines/password_reset_prompt_v1.0.json")

    assert ("TC-001", "unsupported-numeric-value") in findings
    assert ("TC-002", "unregistered-reset-link-claim") in findings
    assert ("TC-003", "unsupported-numeric-value") in findings
    assert ("TC-005", "unsupported-numeric-value") in findings
    assert ("TC-006", "suspicious-edge-classification") in findings


def test_v12_no_longer_flags_the_unregistered_backend_claim() -> None:
    findings = finding_ids("evals/experiments/password_reset_prompt_v1.2.json")

    assert ("TC-0", "unregistered-reset-link-claim") not in findings
    assert ("TC-001", "unsupported-numeric-value") in findings
    assert ("TC-006", "suspicious-edge-classification") in findings


def test_report_is_json_serializable() -> None:
    suite = load_suite("evals/baselines/password_reset_prompt_v1.0.json")

    report = evaluate_quality(REQUEST, suite)
    serialized = json.dumps(report.model_dump(mode="json"))

    assert '"source_story_id": "US-001"' in serialized
    assert report.passed is False


def test_gemma_report_ignores_step_reference_and_visible_confirmation() -> None:
    findings = finding_ids(
        "evals/experiments/password_reset_prompt_v1.2_gemma3_12b.json"
    )

    assert ("TC-002", "unsupported-numeric-value") not in findings
    assert ("TC-002", "unregistered-reset-link-claim") not in findings


def test_saved_gemma_report_matches_the_current_quality_rules() -> None:
    suite = load_suite(
        "evals/experiments/password_reset_prompt_v1.2_gemma3_12b.json"
    )
    expected = evaluate_quality(REQUEST, suite)
    saved = json.loads(
        (
            ROOT
            / "evals"
            / "experiments"
            / "password_reset_prompt_v1.2_gemma3_12b_quality.json"
        ).read_text(encoding="utf-8")
    )

    assert saved == expected.model_dump(mode="json")
