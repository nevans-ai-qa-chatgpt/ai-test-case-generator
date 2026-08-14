import json
from dataclasses import dataclass

import pytest

from ai_test_case_generator.model_output import (
    ModelTestCase,
    ModelTestStep,
    ModelTestSuite,
)
from ai_test_case_generator.models import (
    CasePlanItem,
    GenerationRequest,
    Priority,
    TestCase as CaseModel,
    TestCategory as Category,
    TestStep as StepModel,
    TestSuite as SuiteModel,
    UserStory,
)
from ai_test_case_generator.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from ai_test_case_generator.providers import ProviderError
from ai_test_case_generator.providers.ollama import OllamaTestCaseProvider


@dataclass
class RecordingTransport:
    response: dict[str, object]
    url: str | None = None
    payload: dict[str, object] | None = None
    timeout: float | None = None

    def post(
        self,
        url: str,
        payload: dict[str, object],
        *,
        timeout: float,
    ) -> dict[str, object]:
        self.url = url
        self.payload = payload
        self.timeout = timeout
        return self.response


def make_request() -> GenerationRequest:
    return GenerationRequest(
        story=UserStory(
            id="US-001",
            title="Reset a forgotten password",
            narrative="As a user, I want to reset my password to regain access.",
            acceptance_criteria=["A reset link expires after a limited time."],
        ),
        categories=[Category.FUNCTIONAL],
        case_plan=[
            CasePlanItem(
                id="PLAN-001",
                requirement_id="AC-001",
                category=Category.FUNCTIONAL,
            )
        ],
    )


def make_suite() -> SuiteModel:
    return SuiteModel(
        source_story_id="US-001",
        test_cases=[
            CaseModel(
                id="TC-001",
                plan_id="PLAN-001",
                title="Request a password reset",
                category=Category.FUNCTIONAL,
                priority=Priority.HIGH,
                objective="Verify the primary reset workflow.",
                preconditions=["A registered account exists."],
                steps=[
                    StepModel(
                        number=1,
                        action="Request a reset link.",
                        expected_result="A time-limited link is sent.",
                    )
                ],
                source_requirements=["A reset link expires after a limited time."],
            )
        ],
    )


def make_model_suite() -> ModelTestSuite:
    return ModelTestSuite(
        source_story_id="US-001",
        test_cases=[
            ModelTestCase(
                id="TC-001",
                plan_id="PLAN-001",
                title="Request a password reset",
                priority=Priority.HIGH,
                objective="Verify the primary reset workflow.",
                preconditions=["A registered account exists."],
                steps=[
                    ModelTestStep(
                        action="Request a reset link.",
                        expected_result="A time-limited link is sent.",
                    )
                ],
            )
        ],
    )


def test_provider_requests_and_validates_structured_output() -> None:
    suite = make_suite()
    transport = RecordingTransport(
        {
            "message": {
                "role": "assistant",
                "content": make_model_suite().model_dump_json(),
            },
            "prompt_eval_count": 120,
            "eval_count": 80,
        }
    )
    provider = OllamaTestCaseProvider(
        model="local-test",
        base_url="http://localhost:9999/",
        timeout=12.5,
        transport=transport,
    )

    result = provider.generate(make_request())

    assert result == suite
    assert transport.url == "http://localhost:9999/api/chat"
    assert transport.timeout == 12.5
    assert transport.payload is not None
    assert transport.payload["model"] == "local-test"
    assert transport.payload["stream"] is False
    schema = transport.payload["format"]
    assert schema["properties"]["test_cases"]["maxItems"] == 1
    assert schema["$defs"]["ModelTestCase"]["properties"]["steps"]["maxItems"] == 6
    assert "number" not in schema["$defs"]["ModelTestStep"]["properties"]
    plan_id = schema["$defs"]["ModelTestCase"]["properties"]["plan_id"]
    assert plan_id["enum"] == ["PLAN-001"]
    assert schema["properties"]["test_cases"]["maxItems"] == 1
    assert schema["properties"]["coverage_gaps"]["maxItems"] == 0
    assert transport.payload["options"] == {"temperature": 0}
    assert provider.last_usage is not None
    assert provider.last_usage.total_tokens == 200


def test_prompt_separates_instructions_from_request_data() -> None:
    transport = RecordingTransport(
        {
            "message": {
                "role": "assistant",
                "content": make_model_suite().model_dump_json(),
            }
        }
    )
    provider = OllamaTestCaseProvider(transport=transport)

    provider.generate(make_request())

    assert transport.payload is not None
    messages = transport.payload["messages"]
    assert isinstance(messages, list)
    assert SYSTEM_PROMPT in messages[0]["content"]
    assert "JSON Schema" in messages[0]["content"]
    assert f"Prompt version: {PROMPT_VERSION}" in messages[1]["content"]
    assert '"id": "US-001"' in messages[1]["content"]


def test_invalid_model_json_reports_safe_validation_locations() -> None:
    raw_response = json.dumps({"wrong": True})
    transport = RecordingTransport(
        {"message": {"role": "assistant", "content": raw_response}}
    )
    provider = OllamaTestCaseProvider(transport=transport)

    with pytest.raises(
        ProviderError,
        match=r"source_story_id \(missing\)",
    ) as error:
        provider.generate(make_request())

    assert "wrong" not in str(error.value)
    assert provider.last_raw_response == raw_response


def test_transport_failure_is_wrapped_without_exposing_details() -> None:
    class FailingTransport:
        def post(
            self,
            url: str,
            payload: dict[str, object],
            *,
            timeout: float,
        ) -> dict[str, object]:
            raise RuntimeError("sensitive local details")

    provider = OllamaTestCaseProvider(
        model="local-test",
        transport=FailingTransport(),
    )

    with pytest.raises(ProviderError, match="local-test") as error:
        provider.generate(make_request())

    assert "sensitive local details" not in str(error.value)


def test_timeout_error_explains_how_long_the_provider_waited() -> None:
    class TimingOutTransport:
        def post(
            self,
            url: str,
            payload: dict[str, object],
            *,
            timeout: float,
        ) -> dict[str, object]:
            raise TimeoutError

    provider = OllamaTestCaseProvider(
        model="local-test",
        timeout=45,
        transport=TimingOutTransport(),
    )

    with pytest.raises(ProviderError, match="timed out after 45 seconds"):
        provider.generate(make_request())


def test_model_backed_generation_requires_an_explicit_case_plan() -> None:
    provider = OllamaTestCaseProvider(
        transport=RecordingTransport({"message": {"content": "{}"}})
    )
    request = make_request().model_copy(update={"case_plan": []})

    with pytest.raises(ProviderError, match="requires a case plan"):
        provider.generate(request)
