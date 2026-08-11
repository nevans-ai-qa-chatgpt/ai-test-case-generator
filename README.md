# AI Test Case Generator

Convert a user story and its acceptance criteria into structured, validated
test cases. This is the first project in the `nevans-ai-qa-chatgpt`
portfolio roadmap.

## Why this project starts with schemas

Large-language-model output is untrusted application input. The generator will
therefore accept and return explicit Pydantic models rather than free-form
text. This makes results machine-readable, rejectable when malformed, and
testable without calling an AI service.

## Current milestone: domain contract

The repository currently defines:

- A structured user story with optional acceptance criteria
- Functional, negative, and edge-case test categories
- Priority, preconditions, numbered steps, and expected results
- Traceability from each test case back to requirements
- Validation for unknown fields, duplicate IDs, and invalid step numbering

The next milestone will add the generation service behind an interchangeable
provider interface.

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

1. Domain contract and validation (current)
2. Deterministic fake AI provider
3. Test-case generation service and prompt boundary
4. Command-line interface
5. OpenAI provider integration
6. Evaluation dataset, CI, and portfolio documentation

