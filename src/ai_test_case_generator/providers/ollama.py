"""Ollama implementation of the provider contract."""

import json
from typing import Protocol
from urllib.request import Request, urlopen

from pydantic import ValidationError

from ai_test_case_generator.model_output import (
    ModelTestSuite,
    model_output_json_schema,
)
from ai_test_case_generator.models import GenerationRequest, TestSuite
from ai_test_case_generator.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from ai_test_case_generator.providers.base import ProviderError, TokenUsage

DEFAULT_OLLAMA_MODEL = "qwen3:4b-instruct"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 300.0


class _JsonTransport(Protocol):
    def post(
        self,
        url: str,
        payload: dict[str, object],
        *,
        timeout: float,
    ) -> dict[str, object]: ...


class _UrllibJsonTransport:
    """Send JSON with the Python standard library."""

    def post(
        self,
        url: str,
        payload: dict[str, object],
        *,
        timeout: float,
    ) -> dict[str, object]:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("Ollama returned a non-object JSON response")
        return result


class OllamaTestCaseProvider:
    """Generate Pydantic-validated test suites through a local Ollama server."""

    name = "ollama"
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        *,
        model: str = DEFAULT_OLLAMA_MODEL,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        transport: _JsonTransport | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport or _UrllibJsonTransport()
        self.last_usage: TokenUsage | None = None
        self.last_raw_response: str | None = None

    def generate(self, request: GenerationRequest) -> TestSuite:
        """Request structured JSON from Ollama and validate it locally."""
        self.last_usage = None
        self.last_raw_response = None
        schema = model_output_json_schema(request)
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{SYSTEM_PROMPT}\n"
                        "Return only JSON matching this JSON Schema:\n"
                        f"{json.dumps(schema, separators=(',', ':'))}"
                    ),
                },
                {"role": "user", "content": build_user_prompt(request)},
            ],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0},
        }

        try:
            response = self._transport.post(
                f"{self.base_url}/api/chat",
                payload,
                timeout=self.timeout,
            )
            self.last_usage = _extract_usage(response)
            message = response["message"]
            if not isinstance(message, dict):
                raise TypeError("Ollama response message is not an object")
            content = message["content"]
            if not isinstance(content, str):
                raise TypeError("Ollama response content is not text")
            self.last_raw_response = content
            model_suite = ModelTestSuite.model_validate_json(content)
            return model_suite.to_test_suite(request)
        except TimeoutError as error:
            raise ProviderError(
                f"Ollama request timed out after {self.timeout:g} seconds "
                f"for model {self.model!r}"
            ) from error
        except ValidationError as error:
            raise ProviderError(
                "Ollama returned output that failed model schema validation: "
                f"{_validation_error_summary(error)}"
            ) from error
        except Exception as error:
            raise ProviderError(
                f"Ollama request failed for model {self.model!r} at {self.base_url}"
            ) from error


def _validation_error_summary(error: ValidationError) -> str:
    """Describe contract failures without exposing generated field values."""

    summaries = []
    for detail in error.errors(include_input=False, include_url=False):
        if detail["type"] == "extra_forbidden":
            location = "<extra field>"
        else:
            location = ".".join(str(part) for part in detail["loc"]) or "root"
        summaries.append(f"{location} ({detail['type']})")
    return ", ".join(summaries)


def _extract_usage(response: dict[str, object]) -> TokenUsage | None:
    if "prompt_eval_count" not in response and "eval_count" not in response:
        return None
    input_tokens = int(response.get("prompt_eval_count", 0) or 0)
    output_tokens = int(response.get("eval_count", 0) or 0)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )
