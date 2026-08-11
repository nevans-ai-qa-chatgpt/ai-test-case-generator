"""The boundary between the application and a test-case generator."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ai_test_case_generator.models import GenerationRequest, TestSuite


class ProviderError(RuntimeError):
    """Raised when a generation backend cannot return a usable response."""


@dataclass(frozen=True)
class TokenUsage:
    """Token counts reported by a metered provider."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


@runtime_checkable
class TestCaseProvider(Protocol):
    """Generate a validated suite for one request."""

    @property
    def name(self) -> str:
        """Return the stable provider identifier."""
        ...

    def generate(self, request: GenerationRequest) -> TestSuite:
        """Generate test cases or raise a provider-specific error."""
        ...
