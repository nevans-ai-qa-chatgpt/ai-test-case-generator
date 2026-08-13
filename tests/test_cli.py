import json
from pathlib import Path

from ai_test_case_generator.cli import _make_provider, main
from ai_test_case_generator.models import TestSuite as SuiteModel


def write_request(path: Path, categories: list[str] | None = None) -> None:
    request = {
        "story": {
            "id": "US-001",
            "title": "Reset a forgotten password",
            "narrative": "As a user, I want to reset my password to regain access.",
        },
        "categories": categories or ["functional", "negative", "edge"],
    }
    path.write_text(json.dumps(request), encoding="utf-8")


def test_generate_writes_a_valid_suite(tmp_path: Path) -> None:
    input_path = tmp_path / "request.json"
    output_path = tmp_path / "suite.json"
    write_request(input_path)

    exit_code = main(
        [
            "generate",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )

    suite = SuiteModel.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert suite.source_story_id == "US-001"
    assert len(suite.test_cases) == 3


def test_generate_respects_requested_categories(tmp_path: Path) -> None:
    input_path = tmp_path / "request.json"
    output_path = tmp_path / "suite.json"
    write_request(input_path, categories=["edge"])

    exit_code = main(
        [
            "generate",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )

    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert [case["category"] for case in output["test_cases"]] == ["edge"]


def test_existing_output_is_not_replaced_without_force(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "request.json"
    output_path = tmp_path / "suite.json"
    write_request(input_path)
    output_path.write_text("keep me", encoding="utf-8")

    exit_code = main(
        [
            "generate",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assert output_path.read_text(encoding="utf-8") == "keep me"
    assert "use --force" in capsys.readouterr().err


def test_force_replaces_an_existing_output(tmp_path: Path) -> None:
    input_path = tmp_path / "request.json"
    output_path = tmp_path / "suite.json"
    write_request(input_path)
    output_path.write_text("replace me", encoding="utf-8")

    exit_code = main(
        [
            "generate",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--force",
        ]
    )

    assert exit_code == 0
    SuiteModel.model_validate_json(output_path.read_text(encoding="utf-8"))


def test_invalid_request_returns_a_user_readable_error(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "request.json"
    output_path = tmp_path / "suite.json"
    input_path.write_text('{"story": {}}', encoding="utf-8")

    exit_code = main(
        [
            "generate",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assert not output_path.exists()
    assert "validation errors for GenerationRequest" in capsys.readouterr().err


def test_openai_provider_requires_an_explicit_api_key(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    input_path = tmp_path / "request.json"
    output_path = tmp_path / "suite.json"
    write_request(input_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "generate",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--provider",
            "openai",
        ]
    )

    assert exit_code == 2
    assert not output_path.exists()
    assert "OPENAI_API_KEY is not set" in capsys.readouterr().err


def test_ollama_provider_uses_local_defaults_without_an_api_key(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provider = _make_provider(
        "ollama",
        model=None,
        ollama_url="http://localhost:11434",
        ollama_timeout=300,
        reasoning_effort="low",
    )

    assert provider.name == "ollama"
    assert provider.model == "qwen3:4b-instruct"
    assert provider.base_url == "http://localhost:11434"
    assert provider.timeout == 300


def test_generate_can_write_a_machine_readable_quality_report(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "request.json"
    output_path = tmp_path / "suite.json"
    report_path = tmp_path / "quality.json"
    write_request(input_path)

    exit_code = main(
        [
            "generate",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--quality-report",
            str(report_path),
        ]
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report == {
        "source_story_id": "US-001",
        "findings": [],
        "passed": True,
    }
    assert "quality gate: no advisory findings" in capsys.readouterr().err


def test_quality_report_cannot_replace_the_generated_suite(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "request.json"
    output_path = tmp_path / "suite.json"
    write_request(input_path)

    exit_code = main(
        [
            "generate",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--quality-report",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assert not output_path.exists()
    assert "must differ" in capsys.readouterr().err


def test_validate_evals_reports_dataset_summary(capsys) -> None:
    dataset_path = Path(__file__).parents[1] / "evals" / "dataset.json"

    exit_code = main(["validate-evals", "--dataset", str(dataset_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "valid (8 cases" in output
    assert "edge=7" in output
    assert "functional=8" in output
    assert "negative=6" in output


def test_validate_evals_rejects_an_invalid_dataset(
    tmp_path: Path,
    capsys,
) -> None:
    dataset_path = tmp_path / "invalid.json"
    dataset_path.write_text(
        '{"schema_version": "1.0", "cases": []}',
        encoding="utf-8",
    )

    exit_code = main(["validate-evals", "--dataset", str(dataset_path)])

    assert exit_code == 2
    assert "validation error" in capsys.readouterr().err


def test_run_evals_can_select_and_resume_a_case(
    tmp_path: Path,
    capsys,
) -> None:
    dataset_path = Path(__file__).parents[1] / "evals" / "dataset.json"
    output_dir = tmp_path / "fake-run"
    command = [
        "run-evals",
        "--dataset",
        str(dataset_path),
        "--output-dir",
        str(output_dir),
        "--case",
        "EVAL-001",
    ]

    first_exit_code = main(command)
    first_output = capsys.readouterr().out
    second_exit_code = main(command)
    second_output = capsys.readouterr().out

    assert first_exit_code == 0
    assert "completed=1, skipped=0, failed=0" in first_output
    assert second_exit_code == 0
    assert "completed=0, skipped=1, failed=0" in second_output


def test_run_evals_rejects_an_unknown_case(tmp_path: Path, capsys) -> None:
    dataset_path = Path(__file__).parents[1] / "evals" / "dataset.json"

    exit_code = main(
        [
            "run-evals",
            "--dataset",
            str(dataset_path),
            "--output-dir",
            str(tmp_path / "run"),
            "--case",
            "EVAL-999",
        ]
    )

    assert exit_code == 2
    assert "unknown evaluation case ID" in capsys.readouterr().err
