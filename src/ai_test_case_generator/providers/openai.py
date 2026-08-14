"""OpenAI Responses API implementation of the provider contract."""

from typing import Protocol

from openai import OpenAI

from ai_test_case_generator.model_output import ModelTestSuite
from ai_test_case_generator.models import GenerationRequest, TestSuite
from ai_test_case_generator.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from ai_test_case_generator.providers.base import ProviderError, TokenUsage

DEFAULT_OPENAI_MODEL = "gpt-5.6-terra"
DEFAULT_REASONING_EFFORT = "low"


class _ResponsesAPI(Protocol):
    def parse(self, **kwargs: object) -> object: ...


class _OpenAIClient(Protocol):
    responses: _ResponsesAPI


class OpenAITestCaseProvider:
    """Generate Pydantic-validated test suites through OpenAI Structured Outputs."""

    name = "openai"
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        *,
        model: str = DEFAULT_OPENAI_MODEL,
        reasoning_effort: str = DEFAULT_REASONING_EFFORT,
        api_key: str | None = None,
        client: _OpenAIClient | None = None,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self._client = client if client is not None else OpenAI(api_key=api_key)
        self.last_usage: TokenUsage | None = None

    def generate(self, request: GenerationRequest) -> TestSuite:
        """Request a structured suite without performing repair or retry loops."""
        if not request.case_plan:
            raise ProviderError("model-backed generation requires a case plan")
        try:
            response = self._client.responses.parse(
                model=self.model,
                reasoning={"effort": self.reasoning_effort},
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(request)},
                ],
                text_format=ModelTestSuite,
            )
        except Exception as error:
            raise ProviderError(
                f"OpenAI request failed for model {self.model!r}"
            ) from error

        self.last_usage = _extract_usage(response)
        parsed = getattr(response, "output_parsed", None)
        if not isinstance(parsed, ModelTestSuite):
            raise ProviderError("OpenAI response did not contain parsed model output")
        try:
            return parsed.to_test_suite(request)
        except ValueError as error:
            raise ProviderError(
                "OpenAI response did not match the authorized case plan"
            ) from error


def _extract_usage(response: object) -> TokenUsage | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return TokenUsage(
        input_tokens=int(getattr(usage, "input_tokens", 0)),
        output_tokens=int(getattr(usage, "output_tokens", 0)),
        total_tokens=int(getattr(usage, "total_tokens", 0)),
    )
