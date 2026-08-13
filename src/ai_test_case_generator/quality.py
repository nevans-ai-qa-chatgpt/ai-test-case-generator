"""Deterministic advisory checks for generated test-suite quality."""

import re
from enum import StrEnum

from pydantic import Field, computed_field

from ai_test_case_generator.models import (
    GenerationRequest,
    StrictModel,
    TestCase,
    TestCategory,
    TestSuite,
)

_NUMBER_PATTERN = re.compile(r"(?<![\w-])\d+(?:\.\d+)?%?")
_QUOTED_TEXT_PATTERN = re.compile(r"(?<!\w)(?:'([^'\n]{4,})'|\"([^\"\n]{4,})\")(?!\w)")
_INVALID_BEHAVIOR_PATTERN = re.compile(
    r"\b(invalid|malformed|empty|missing|violat(?:e|es|ion)|does not meet|rejected)\b",
    re.IGNORECASE,
)
_UNREGISTERED_LINK_PATTERNS = (
    re.compile(
        r"\b(?:system|backend|service)\b[^.]{0,80}\b(?:send|sends)\b"
        r"[^.]{0,80}\breset link\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:send|sends)\b[^.]{0,80}\breset link\b[^.]{0,80}"
        r"\bregardless of\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:unregistered|provided)\b[^.]{0,80}\b(?:email|address|user)\b"
        r"[^.]{0,80}\b(?:receive|receives)\b[^.]{0,40}\breset link\b",
        re.IGNORECASE,
    ),
)


class QualitySeverity(StrEnum):
    """Advisory severity levels, reserved for future gate calibration."""

    WARNING = "warning"


class QualityFinding(StrictModel):
    """One explainable quality concern tied to a generated test case."""

    rule_id: str = Field(min_length=1)
    severity: QualitySeverity = QualitySeverity.WARNING
    test_case_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)


class QualityReport(StrictModel):
    """Advisory findings for one generated suite."""

    source_story_id: str = Field(min_length=1)
    findings: list[QualityFinding] = Field(default_factory=list)

    @computed_field
    @property
    def passed(self) -> bool:
        """Return true when no advisory checks found a concern."""
        return not self.findings


def evaluate_quality(
    request: GenerationRequest,
    suite: TestSuite,
) -> QualityReport:
    """Run deterministic checks without changing or rejecting model output."""
    source_text = "\n".join(
        [
            request.story.title,
            request.story.narrative,
            *request.story.acceptance_criteria,
        ]
    )
    allowed_numbers = set(_NUMBER_PATTERN.findall(source_text))
    findings: list[QualityFinding] = []

    for test_case in suite.test_cases:
        generated_text = "\n".join(_reviewable_text(test_case))
        findings.extend(
            _case_findings(
                test_case,
                generated_text,
                source_text=source_text,
                allowed_numbers=allowed_numbers,
            )
        )

    return QualityReport(
        source_story_id=suite.source_story_id,
        findings=findings,
    )


def _case_findings(
    test_case: TestCase,
    generated_text: str,
    *,
    source_text: str,
    allowed_numbers: set[str],
) -> list[QualityFinding]:
    findings: list[QualityFinding] = []

    unsupported_numbers = sorted(
        _unsupported_numbers(generated_text, allowed_numbers)
    )
    if unsupported_numbers:
        findings.append(
            QualityFinding(
                rule_id="unsupported-numeric-value",
                test_case_id=test_case.id,
                message="Generated numeric values do not appear in the source request.",
                evidence=unsupported_numbers,
            )
        )

    unsupported_messages = sorted(
        phrase
        for phrase in _quoted_phrases(generated_text)
        if phrase not in source_text
    )
    if unsupported_messages:
        findings.append(
            QualityFinding(
                rule_id="unsupported-quoted-message",
                test_case_id=test_case.id,
                message="Generated quoted text does not appear in the source request.",
                evidence=unsupported_messages,
            )
        )

    if not test_case.preconditions:
        findings.append(
            QualityFinding(
                rule_id="missing-preconditions",
                test_case_id=test_case.id,
                message="The case has no explicit preconditions.",
            )
        )

    if (
        test_case.category is TestCategory.EDGE
        and _INVALID_BEHAVIOR_PATTERN.search(generated_text)
    ):
        findings.append(
            QualityFinding(
                rule_id="suspicious-edge-classification",
                test_case_id=test_case.id,
                message=(
                    "The edge case describes invalid or rejected behavior that may "
                    "belong in the negative category."
                ),
            )
        )

    if (
        "unregistered" in generated_text.casefold()
        and any(
            pattern.search(_without_quoted_phrases(step.expected_result))
            for step in test_case.steps
            for pattern in _UNREGISTERED_LINK_PATTERNS
        )
    ):
        findings.append(
            QualityFinding(
                rule_id="unregistered-reset-link-claim",
                test_case_id=test_case.id,
                message=(
                    "The case may infer reset-link delivery for an unregistered "
                    "address from a user-visible confirmation requirement."
                ),
            )
        )

    return findings


def _reviewable_text(test_case: TestCase) -> list[str]:
    return [
        test_case.title,
        test_case.objective,
        *test_case.preconditions,
        *(step.action for step in test_case.steps),
        *(step.expected_result for step in test_case.steps),
    ]


def _quoted_phrases(text: str) -> set[str]:
    return {
        first or second
        for first, second in _QUOTED_TEXT_PATTERN.findall(text)
        if first or second
    }


def _without_quoted_phrases(text: str) -> str:
    return _QUOTED_TEXT_PATTERN.sub("", text)


def _unsupported_numbers(text: str, allowed_numbers: set[str]) -> set[str]:
    unsupported: set[str] = set()
    for match in _NUMBER_PATTERN.finditer(text):
        value = match.group()
        prefix = text[max(0, match.start() - 8) : match.start()]
        if re.search(r"\bstep\s+$", prefix, re.IGNORECASE):
            continue
        if value not in allowed_numbers:
            unsupported.add(value)
    return unsupported
