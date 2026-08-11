"""The boundary between the application and a test-case generator."""

from typing import Protocol, runtime_checkable

from ai_test_case_generator.models import GenerationRequest, TestSuite


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

