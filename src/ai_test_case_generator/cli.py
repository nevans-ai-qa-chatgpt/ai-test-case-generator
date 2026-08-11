"""Command-line interface for the test-case generator."""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from ai_test_case_generator.models import GenerationRequest
from ai_test_case_generator.providers import (
    FakeTestCaseProvider,
    OpenAITestCaseProvider,
    ProviderError,
    TestCaseProvider,
)
from ai_test_case_generator.providers.openai import (
    DEFAULT_OPENAI_MODEL,
    DEFAULT_REASONING_EFFORT,
)
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
        choices=("fake", "openai"),
        default="fake",
        help="Generation backend (default: fake).",
    )
    generate.add_argument(
        "--model",
        default=DEFAULT_OPENAI_MODEL,
        help=f"OpenAI model (default: {DEFAULT_OPENAI_MODEL}).",
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
                reasoning_effort=args.reasoning_effort,
                force=args.force,
            )
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


def _generate(
    *,
    input_path: Path,
    output_path: Path,
    provider_name: str,
    model: str,
    reasoning_effort: str,
    force: bool,
) -> None:
    if output_path.exists() and not force:
        raise CliError(f"output already exists: {output_path}; use --force to replace it")

    request_data = json.loads(input_path.read_text(encoding="utf-8"))
    request = GenerationRequest.model_validate(request_data)
    provider = _make_provider(
        provider_name,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    service = GenerationService(provider)
    suite = service.generate(request)

    output = json.dumps(
        suite.model_dump(mode="json"),
        indent=2,
        ensure_ascii=False,
    ) + "\n"
    output_path.write_text(output, encoding="utf-8")

    usage = getattr(provider, "last_usage", None)
    if usage is not None:
        print(
            "token usage: "
            f"input={usage.input_tokens}, "
            f"output={usage.output_tokens}, "
            f"total={usage.total_tokens}",
            file=sys.stderr,
        )


def _make_provider(
    name: str,
    *,
    model: str,
    reasoning_effort: str,
) -> TestCaseProvider:
    if name == "fake":
        return FakeTestCaseProvider()
    if name == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise CliError(
                "OPENAI_API_KEY is not set; use --provider fake or configure the key"
            )
        return OpenAITestCaseProvider(
            api_key=api_key,
            model=model,
            reasoning_effort=reasoning_effort,
        )
    raise CliError(f"unknown provider: {name}")


if __name__ == "__main__":
    raise SystemExit(main())
