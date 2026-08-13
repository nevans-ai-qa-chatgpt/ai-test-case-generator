"""Command-line interface for the test-case generator."""

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from ai_test_case_generator.evaluation import load_evaluation_dataset
from ai_test_case_generator.models import GenerationRequest
from ai_test_case_generator.providers import (
    FakeTestCaseProvider,
    OllamaTestCaseProvider,
    OpenAITestCaseProvider,
    ProviderError,
    TestCaseProvider,
)
from ai_test_case_generator.providers.ollama import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
)
from ai_test_case_generator.providers.openai import (
    DEFAULT_OPENAI_MODEL,
    DEFAULT_REASONING_EFFORT,
)
from ai_test_case_generator.quality import QualityReport, evaluate_quality
from ai_test_case_generator.service import GenerationService, ProviderContractError


class CliError(ValueError):
    """An expected command-line failure with a user-readable message."""


def build_parser() -> argparse.ArgumentParser:
    """Build the parser separately so its behavior is straightforward to test."""
    parser = argparse.ArgumentParser(
        prog="ai-test-cases",
        description="Generate validated test cases from a structured user story.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate",
        help="Generate a test suite from a JSON request.",
    )
    generate.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to a GenerationRequest JSON file.",
    )
    generate.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path where the generated TestSuite JSON will be written.",
    )
    generate.add_argument(
        "--provider",
        choices=("fake", "ollama", "openai"),
        default="fake",
        help="Generation backend (default: fake).",
    )
    generate.add_argument(
        "--model",
        default=None,
        help=(
            "Provider model override "
            f"(Ollama: {DEFAULT_OLLAMA_MODEL}; OpenAI: {DEFAULT_OPENAI_MODEL})."
        ),
    )
    generate.add_argument(
        "--ollama-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        help=f"Ollama server URL (default: {DEFAULT_OLLAMA_BASE_URL}).",
    )
    generate.add_argument(
        "--ollama-timeout",
        type=float,
        default=DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        help=(
            "Seconds to wait for local generation "
            f"(default: {DEFAULT_OLLAMA_TIMEOUT_SECONDS:g})."
        ),
    )
    generate.add_argument(
        "--reasoning-effort",
        choices=("none", "low", "medium", "high", "xhigh", "max"),
        default=DEFAULT_REASONING_EFFORT,
        help=f"OpenAI reasoning effort (default: {DEFAULT_REASONING_EFFORT}).",
    )
    generate.add_argument(
        "--force",
        action="store_true",
        help="Replace the output file if it already exists.",
    )
    generate.add_argument(
        "--quality-report",
        type=Path,
        help="Optional path for the advisory quality report JSON.",
    )

    validate_evals = subparsers.add_parser(
        "validate-evals",
        help="Validate an evaluation dataset without calling a model.",
    )
    validate_evals.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to an EvaluationDataset JSON file.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "generate":
            _generate(
                input_path=args.input,
                output_path=args.output,
                provider_name=args.provider,
                model=args.model,
                ollama_url=args.ollama_url,
                ollama_timeout=args.ollama_timeout,
                reasoning_effort=args.reasoning_effort,
                force=args.force,
                quality_report_path=args.quality_report,
            )
        elif args.command == "validate-evals":
            _validate_evals(args.dataset)
    except (CliError, OSError, json.JSONDecodeError, ValidationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except ProviderContractError as error:
        print(f"provider contract error: {error}", file=sys.stderr)
        return 3
    except ProviderError as error:
        print(f"provider error: {error}", file=sys.stderr)
        return 4

    return 0


def _validate_evals(dataset_path: Path) -> None:
    dataset = load_evaluation_dataset(dataset_path)
    category_counts = Counter(
        category.value
        for case in dataset.cases
        for category in case.request.categories
    )
    tag_count = len({tag for case in dataset.cases for tag in case.tags})

    print(
        f"evaluation dataset: valid ({len(dataset.cases)} cases, "
        f"{tag_count} distinct tags)"
    )
    print(
        "requested categories: "
        + ", ".join(
            f"{category}={count}"
            for category, count in sorted(category_counts.items())
        )
    )


def _generate(
    *,
    input_path: Path,
    output_path: Path,
    provider_name: str,
    model: str | None,
    ollama_url: str,
    ollama_timeout: float,
    reasoning_effort: str,
    force: bool,
    quality_report_path: Path | None,
) -> None:
    if (
        quality_report_path is not None
        and quality_report_path.resolve() == output_path.resolve()
    ):
        raise CliError("quality report path must differ from the generated suite path")
    if output_path.exists() and not force:
        raise CliError(f"output already exists: {output_path}; use --force to replace it")
    if quality_report_path is not None and quality_report_path.exists() and not force:
        raise CliError(
            f"quality report already exists: {quality_report_path}; "
            "use --force to replace it"
        )

    request_data = json.loads(input_path.read_text(encoding="utf-8"))
    request = GenerationRequest.model_validate(request_data)
    provider = _make_provider(
        provider_name,
        model=model,
        ollama_url=ollama_url,
        ollama_timeout=ollama_timeout,
        reasoning_effort=reasoning_effort,
    )
    service = GenerationService(provider)
    suite = service.generate(request)
    quality_report = evaluate_quality(request, suite)

    output = json.dumps(
        suite.model_dump(mode="json"),
        indent=2,
        ensure_ascii=False,
    ) + "\n"
    output_path.write_text(output, encoding="utf-8")

    if quality_report_path is not None:
        report_output = json.dumps(
            quality_report.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        ) + "\n"
        quality_report_path.write_text(report_output, encoding="utf-8")

    _print_quality_findings(quality_report)

    usage = getattr(provider, "last_usage", None)
    if usage is not None:
        print(
            "token usage: "
            f"input={usage.input_tokens}, "
            f"output={usage.output_tokens}, "
            f"total={usage.total_tokens}",
            file=sys.stderr,
        )


def _print_quality_findings(report: QualityReport) -> None:
    if report.passed:
        print("quality gate: no advisory findings", file=sys.stderr)
        return

    print(f"quality gate: {len(report.findings)} advisory finding(s)", file=sys.stderr)
    for finding in report.findings:
        evidence = (
            f" evidence={', '.join(finding.evidence)}" if finding.evidence else ""
        )
        print(
            f"quality warning [{finding.rule_id}] {finding.test_case_id}: "
            f"{finding.message}{evidence}",
            file=sys.stderr,
        )


def _make_provider(
    name: str,
    *,
    model: str | None,
    ollama_url: str,
    ollama_timeout: float,
    reasoning_effort: str,
) -> TestCaseProvider:
    if name == "fake":
        return FakeTestCaseProvider()
    if name == "ollama":
        return OllamaTestCaseProvider(
            model=model or DEFAULT_OLLAMA_MODEL,
            base_url=ollama_url,
            timeout=ollama_timeout,
        )
    if name == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise CliError(
                "OPENAI_API_KEY is not set; use --provider fake or configure the key"
            )
        return OpenAITestCaseProvider(
            api_key=api_key,
            model=model or DEFAULT_OPENAI_MODEL,
            reasoning_effort=reasoning_effort,
        )
    raise CliError(f"unknown provider: {name}")


if __name__ == "__main__":
    raise SystemExit(main())
