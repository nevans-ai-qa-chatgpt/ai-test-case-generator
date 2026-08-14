from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from ai_test_case_generator.model_output import (
    ModelTestCase,
    ModelTestStep,
    ModelTestSuite,
)
from ai_test_case_generator.models import (
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
from ai_test_case_generator.providers.openai import OpenAITestCaseProvider


@dataclass
class RecordingResponses:
    response: object
    call: dict[str, object] | None = None

    def parse(self, **kwargs: object) -> object:
        self.call = kwargs
        return self.response


@dataclass
class MockClient:
    responses: RecordingResponses


def make_request() -> GenerationRequest:
    return GenerationRequest(
        story=UserStory(
            id="US-001",
            title="Reset a forgotten password",
            narrative="As a user, I want to reset my password to regain access.",
            acceptance_criteria=["A reset link expires after a limited time."],
        ),
        categories=[Category.FUNCTIONAL],
    )


def make_suite() -> SuiteModel:
    return SuiteModel(
        source_story_id="US-001",
        test_cases=[
            CaseModel(
                id="TC-001",
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
                source_requirements=[
                    "A reset link expires after a limited time."
                ],
            )
        ],
    )


def make_model_suite() -> ModelTestSuite:
    return ModelTestSuite(
        source_story_id="US-001",
        test_cases=[
            ModelTestCase(
                id="TC-001",
                title="Request a password reset",
                category=Category.FUNCTIONAL,
                priority=Priority.HIGH,
                objective="Verify the primary reset workflow.",
                preconditions=["A registered account exists."],
                steps=[
                    ModelTestStep(
                        action="Request a reset link.",
                        expected_result="A time-limited link is sent.",
                    )
                ],
                source_requirement_ids=["AC-001"],
            )
        ],
    )


def test_provider_uses_responses_structured_outputs() -> None:
    response = SimpleNamespace(
        output_parsed=make_model_suite(),
        usage=SimpleNamespace(input_tokens=120, output_tokens=80, total_tokens=200),
    )
    responses = RecordingResponses(response)
    provider = OpenAITestCaseProvider(
        model="gpt-test",
        reasoning_effort="low",
        client=MockClient(responses),
    )

    result = provider.generate(make_request())

    assert result == make_suite()
    assert responses.call is not None
    assert responses.call["model"] == "gpt-test"
    assert responses.call["reasoning"] == {"effort": "low"}
    assert responses.call["text_format"] is ModelTestSuite
    assert provider.last_usage is not None
    assert provider.last_usage.total_tokens == 200


def test_prompt_separates_instructions_from_request_data() -> None:
    response = SimpleNamespace(output_parsed=make_model_suite(), usage=None)
    responses = RecordingResponses(response)
    provider = OpenAITestCaseProvider(client=MockClient(responses))

    provider.generate(make_request())

    assert responses.call is not None
    messages = responses.call["input"]
    assert isinstance(messages, list)
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert f"Prompt version: {PROMPT_VERSION}" in messages[1]["content"]
    assert '"id": "US-001"' in messages[1]["content"]
    assert '"functional"' in messages[1]["content"]


def test_missing_parsed_output_is_a_provider_error() -> None:
    response = SimpleNamespace(output_parsed=None, usage=None)
    provider = OpenAITestCaseProvider(
        client=MockClient(RecordingResponses(response))
    )

    with pytest.raises(ProviderError, match="did not contain"):
        provider.generate(make_request())


def test_unknown_requirement_id_is_a_provider_error() -> None:
    model_suite = make_model_suite()
    unknown_case = model_suite.test_cases[0].model_copy(
        update={"source_requirement_ids": ["AC-999"]}
    )
    response = SimpleNamespace(
        output_parsed=model_suite.model_copy(update={"test_cases": [unknown_case]}),
        usage=None,
    )
    provider = OpenAITestCaseProvider(
        client=MockClient(RecordingResponses(response))
    )

    with pytest.raises(ProviderError, match="unknown requirement ID"):
        provider.generate(make_request())


def test_sdk_failure_is_wrapped_without_exposing_details() -> None:
    class FailingResponses:
        def parse(self, **kwargs: object) -> object:
            raise RuntimeError("sensitive upstream details")

    provider = OpenAITestCaseProvider(
        model="gpt-test",
        client=MockClient(FailingResponses()),  # type: ignore[arg-type]
    )

    with pytest.raises(ProviderError, match="gpt-test") as error:
        provider.generate(make_request())

    assert "sensitive upstream details" not in str(error.value)
