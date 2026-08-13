# AI Test Case Generator

Convert a user story and its acceptance criteria into structured, validated
test cases. This is the first project in the `nevans-ai-qa-chatgpt`
portfolio roadmap.

## Why this project starts with schemas

Large-language-model output is untrusted application input. The generator will
therefore accept and return explicit Pydantic models rather than free-form
text. This makes results machine-readable, rejectable when malformed, and
testable without calling an AI service.

## Current milestone: Resumable evaluation runner

The repository currently defines:

- A structured user story with optional acceptance criteria
- Functional, negative, and edge-case test categories
- Priority, preconditions, numbered steps, and expected results
- Traceability from each test case back to requirements
- Validation for unknown fields, duplicate IDs, and invalid step numbering
- A provider interface that keeps generation backends interchangeable
- A deterministic fake provider for offline development and testing
- A strict service that rejects semantically incorrect provider responses
- A safe command-line workflow using versionable JSON request and result files
- An opt-in OpenAI Responses provider using Pydantic Structured Outputs
- An opt-in Ollama provider for private, per-call-free local generation
- A versioned eight-case evaluation dataset with an independent review rubric
- Offline dataset validation that makes no model calls
- Sequential evaluation runs that preserve progress across failures and stops
- Per-case suites, quality reports, timing, token usage, and status artifacts
- Schema-enforced limits of six test cases and six steps per case

The fake provider intentionally uses fixed templates rather than simulating AI
quality. Its purpose is to exercise the application workflow reliably. The
service also rejects a mismatched story ID, missing requested categories, and
unrequested categories instead of silently repairing model output.

Model-backed output is also reviewed against the grounding and executability
rubric in [`evals/README.md`](evals/README.md). Prompt changes are versioned and
compared against preserved outputs from the same representative requests.

Validate the full evaluation corpus before a model run:

```powershell
ai-test-cases validate-evals --dataset evals/dataset.json
```

This checks structure, identifiers, requested categories, and review metadata;
it does not generate test cases, use tokens, or incur an API charge.

Smoke-test the complete runner without loading a model:

```powershell
ai-test-cases run-evals `
  --dataset evals/dataset.json `
  --output-dir "$env:TEMP\ai-test-case-generator-fake-smoke"
```

Run the dataset against local Ollama by changing the provider and using a new
output directory:

```powershell
ai-test-cases run-evals `
  --dataset evals/dataset.json `
  --output-dir evals/runs/qwen3-4b-prompt-v1.3 `
  --provider ollama
```

Results are saved after every case. Repeating the command skips completed cases
and retries failed or interrupted ones. `--case EVAL-001` limits an invocation
to one case; repeat the option to select multiple cases. See
[`evals/README.md`](evals/README.md) for artifact layout and safety rules.

## Generate test cases

After completing the local setup, run:

```powershell
ai-test-cases generate `
  --input examples/password_reset_request.json `
  --output password_reset_suite.json `
  --provider fake
```

The fake provider is the default, so `--provider fake` is optional. The command
refuses to replace an existing output file unless `--force` is supplied.

## OpenAI provider

The OpenAI provider is never selected implicitly. A live request requires both
`--provider openai` and an `OPENAI_API_KEY` environment variable. API usage is
metered and may incur charges.

```powershell
$env:OPENAI_API_KEY = "your-project-api-key"
ai-test-cases generate `
  --input examples/password_reset_request.json `
  --output password_reset_suite.json `
  --provider openai `
  --model gpt-5.6-terra `
  --reasoning-effort low
```

The key must not be committed. The CLI prints reported token usage after a live
request so cost can be monitored. Automated tests inject a mock client and never
contact the OpenAI API.

## Ollama provider

The Ollama provider calls a model running on your computer at
`http://127.0.0.1:11434`. It sends the Pydantic JSON Schema to Ollama and then
validates the returned JSON again before the service accepts it. No API key is
required, and no per-call provider fee is charged.

Install Ollama, download the default instruction-following model, and ensure the
local server is running:

```powershell
ollama pull qwen3:4b-instruct
ollama serve
```

Then generate a suite:

```powershell
ai-test-cases generate `
  --input examples/password_reset_request.json `
  --output password_reset_suite.json `
  --provider ollama
```

Use `--model` to select another installed model, `--ollama-url` to connect to
an Ollama server at a different address, or `--ollama-timeout` when slower
hardware needs longer than the 300-second default. Automated tests use a fake
HTTP transport and do not require Ollama or a downloaded model.

## Advisory quality gate

Every generated suite passes through deterministic advisory checks after schema
and service validation. The gate reports unsupported numeric values, invented
quoted messages, missing preconditions, suspicious edge-case classification,
and reset-link delivery claims for unregistered addresses. These findings do
not block output while the heuristics are being calibrated.

Add `--quality-report` to save the findings as machine-readable JSON:

```powershell
ai-test-cases generate `
  --input examples/password_reset_request.json `
  --output password_reset_suite.json `
  --provider ollama `
  --quality-report password_reset_quality.json
```

The gate is intentionally explainable and incomplete: it can flag known failure
patterns but cannot prove that every generated behavior is supported. Human
review remains required. Local comparison results for Qwen3 4B and Gemma 3 12B
are recorded in [`evals/README.md`](evals/README.md).

## Example

```python
from ai_test_case_generator.models import UserStory

story = UserStory(
    id="US-001",
    title="Reset a forgotten password",
    narrative=(
        "As a user, I want to reset my password so that I can regain access."
    ),
    acceptance_criteria=[
        "A registered user receives a time-limited reset link.",
        "The new password must satisfy the password policy.",
    ],
)
```

See [`examples/password_reset.json`](examples/password_reset.json) for a full
input/output example.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

## Planned milestones

1. Domain contract and validation (complete)
2. Deterministic fake AI provider (complete)
3. Strict test-case generation service (complete)
4. File-based command-line interface (complete)
5. OpenAI provider integration (mock-tested; live test deferred)
6. Local Ollama provider integration (complete)
7. Representative evaluation dataset (complete)
8. Resumable evaluation runner (complete)
9. Cross-case quality calibration
10. CI and portfolio documentation
