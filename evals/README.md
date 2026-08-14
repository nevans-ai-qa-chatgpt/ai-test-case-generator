# Local Model Evaluation

This directory preserves representative model outputs so prompt changes can be
compared against the same input instead of judged from memory.

## Representative dataset

`dataset.json` contains eight versioned inputs chosen to expose different
failure modes: security and privacy, numeric boundaries, file constraints,
state transitions, daylight-saving time, role authorization, discount math,
and restraint when requirements are sparse. Each case contains two kinds of
data that are intentionally kept separate:

- `request` is the only content sent to a generation provider.
- `review_assertions` and `forbidden_assumptions` are the independent rubric
  used by a human reviewer; they must never be included in the model prompt.

Validate the dataset without loading or calling any model:

```powershell
ai-test-cases validate-evals --dataset evals/dataset.json
```

The first full-dataset run should preserve one output and one quality report per
case, along with the provider, model, prompt version, token counts, and runtime.
Run one model configuration at a time so differences can be attributed to a
controlled change. The current password-reset artifacts predate this dataset
layout and remain as historical evidence.

## Resumable runs

Use `run-evals` to process cases sequentially and save each result immediately.
Start with the fake provider to verify the workflow without loading a model:

```powershell
ai-test-cases run-evals `
  --dataset evals/dataset.json `
  --output-dir "$env:TEMP\ai-test-case-generator-fake-smoke"
```

For the default local model, use a separate output directory named for the
configuration:

```powershell
ai-test-cases run-evals `
  --dataset evals/dataset.json `
  --output-dir evals/runs/qwen3-4b-prompt-v1.4 `
  --provider ollama
```

The runner creates an immutable `run.json` manifest and then writes
`suite.json`, `quality.json`, and `result.json` under `cases/EVAL-NNN/`. If an
Ollama response reaches the application but fails schema or service validation,
the exact model text is retained as `raw_response.txt` beside the failed
`result.json`. A successful retry removes that failure-only artifact. A second
invocation with the same command skips completed cases and retries failed or
interrupted cases. Pressing Ctrl+C is therefore safe after earlier cases have
completed.

Use `--case EVAL-001` to run a single case. Repeat `--case` to select several.
Use `--force` only when you intentionally want to replace completed results.
Changing the dataset, provider, model, prompt version, or relevant provider
settings requires a new output directory so experiment results cannot be mixed.

## Qwen dataset canary

`runs/qwen3-4b-prompt-v1.2/` records the first attempt to run `EVAL-001` with
the default local model and prompt v1.2. The clean attempt reached the
configured 600-second timeout and produced no valid suite, so its `result.json`
is intentionally a failed result.

The Ollama server remained healthy, but its diagnostic log showed more than
3,100 decoded tokens at about 5.4 tokens per second, followed by a context shift
at the 4,096-token context limit. This indicates an unbounded-generation
problem rather than a malformed dataset or unavailable model. Prompt v1.2 asks
for one or more cases per category but does not set a compactness or case-count
limit; `EVAL-001` exposed that weakness before an eight-case run consumed hours.

Do not continue the full Qwen dataset run with this configuration. The next
controlled experiment should bound the number or size of generated cases while
keeping the model, dataset, schema, and temperature unchanged. Simply raising
the timeout or context limit would increase resource use without addressing the
measured verbosity.

Prompt v1.3 is the controlled follow-up: the output contract and prompt both
limit a suite to six cases and each case to six steps. Within those bounds, the
model must cover all requested categories first and then prioritize distinct,
high-risk requirements. The dataset, Qwen model, temperature, and hardware stay
unchanged so the canary comparison isolates this output-bound change.

The v1.3 canary improved termination but still failed the complete contract:

- Qwen finished generation in about 243-251 seconds instead of timing out.
- Output fell from more than 3,100 unfinished tokens to roughly 1,437 tokens.
- The response finished without a context shift or truncation.
- Pydantic rejected the first test case at its model-level validator. The only
  such validator on `TestCase` checks consecutive step numbering, so the model
  did not number that case's steps consecutively from 1.

This confirms that explicit limits fixed the measured verbosity failure, but
the canary remains failed because bounded output is not sufficient unless it
also passes the existing contract. The full eight-case Qwen run remains paused.

Prompt v1.4 removes step numbers from the model-facing schema. The order of the
generated step list carries the model's sequencing decision; application code
then assigns consecutive display numbers while constructing the public
`TestSuite`. This does not repair or reinterpret generated content. It moves a
deterministic presentation field out of the probabilistic model's job while
leaving content, category, traceability, and service validation strict.

The v1.4 `EVAL-001` canary completed successfully in 285.5 seconds using 1,043
input tokens and 1,498 output tokens. The provider schema, conversion, public
domain contract, service checks, and artifact runner all passed. Every saved
case has consecutive step numbers assigned from list order.

The generated content still fails the quality bar with 10 advisory findings:

- All six cases omit preconditions.
- TC-004 invents malformed-email behavior and traces it to a prompt instruction
  instead of an actual story requirement.
- TC-005 invents a 31-minute value.
- TC-006 invents an eight-character password rule and composition rules.
- TC-006 treats password-policy rejection as an edge case instead of negative.
- Several cases assume redirects, messages, or backend state not stated in the
  acceptance criteria.

The canary therefore proves that deterministic numbering removed the structural
failure, not that Qwen output is ready for unattended use. The full dataset run
remains paused until the next quality-focused decision.

Prompt v1.5 is the controlled grounding follow-up. Model-backed cases must now
contain at least one precondition and one source citation. The service accepts a
citation only when it exactly matches a complete acceptance criterion (or the
complete narrative when no criteria exist), and it requires every authoritative
requirement to be cited somewhere in the suite. The prompt also states that
requested categories do not authorize invented behavior and explicitly forbids
unsupported examples, navigation, and prompt text used as traceability.

The v1.5 `EVAL-001` canary completed in 310.0 seconds using 1,174 input
tokens and 1,676 output tokens. It passed the new contract: all six cases have
preconditions, every citation exactly matches request text, and all four
acceptance criteria are cited. Automated findings decreased only from 10 to 9.

Manual review shows no meaningful semantic-quality gain:

- TC-001 invents a `Forgot Password` label and a `3-30 minutes` interval.
- TC-002 invents exact confirmation wording.
- TC-003 assumes a redirect and an unspecified error message.
- TC-004 still invents six- and eight-character password examples and remains
  incorrectly classified as edge behavior.
- TC-005 still invents malformed-email validation despite citing unrelated
  reset-link requirements.
- TC-006 invents clock times and a 31-minute value.
- Several preconditions themselves assume undocumented validation mechanisms or
  policy details.

Exact citations prevent fabricated traceability, but a small model can still
attach unsupported claims to valid citations. Prompt hardening has reached
diminishing returns for this canary. Keep the full Qwen run paused; the next
useful comparison should hold prompt v1.5 constant and test a stronger model.

## Gemma comparison with prompt v1.5

`runs/gemma3-12b-prompt-v1.5/` records the stronger-model follow-up on the same
`EVAL-001` request, prompt v1.5, model-facing schema, temperature-zero setting,
and CPU-only hardware. The timeout ceiling was raised from 600 to 900 seconds
only so the slower model could return a result; it is recorded in `run.json`
and is not treated as an equivalent operational budget.

The original Gemma run returned after 653.9 seconds, exceeding the Qwen run's
600-second ceiling, and the service rejected its suite because TC-006 cited
text that was not an exact acceptance criterion. After failure-response capture
was added, a controlled retry reproduced the same error in 614.4 seconds and
preserved the generated JSON in `raw_response.txt`. TC-006 cites an empty
string and invents both empty-email submission behavior and a required-field
error that are absent from the request.

The runner correctly records a failed `ProviderContractError` result and does
not write `suite.json` or `quality.json` for the invalid suite. Token usage and
advisory finding counts are unavailable because generation did not cross the
service boundary.

| Model | Contract result | Duration | Relative duration |
| --- | --- | ---: | ---: |
| `qwen3:4b-instruct` | Pass; 9 advisory findings | 310.0 s | 1.00x |
| `gemma3:12b` | Fail; empty unsupported citation | 614.4 s | 1.98x |

This canary does not support switching the local default to Gemma. Qwen remains
the faster development model and is the only one of the two that passes the
v1.5 contract on this input, although its nine findings still require human
review. Keep the full dataset run paused: one input is insufficient for a broad
model decision, and neither result meets the unattended-generation quality bar.

## Review rubric

Evaluate each generated suite on five dimensions:

1. **Contract validity**: The JSON matches `TestSuite`, IDs are unique, steps are
   consecutive, and the requested story and categories are preserved.
2. **Requirement coverage**: Every acceptance criterion has meaningful positive
   or negative coverage and each requested category is represented.
3. **Grounding**: Expected behavior comes only from the supplied story and
   acceptance criteria. Unspecified limits, policies, timings, and backend
   effects are not invented.
4. **Classification**: Functional cases cover supported workflows, negative
   cases cover invalid or rejected behavior, and edge cases cover boundaries or
   state transitions.
5. **Executability**: Preconditions establish required state, steps separate
   distinct actions, and expected results are observable without adding product
   requirements.

## Baseline findings

`baselines/password_reset_prompt_v1.0.json` is the first live output from
`qwen3:4b-instruct` using prompt version 1.0. It passes contract validity and
basic coverage, but it has measured content defects:

- TC-002 incorrectly says an unregistered account receives a reset link.
- TC-001, TC-003, TC-004, and TC-005 invent timing or policy values.
- TC-006 classifies malformed input as an edge case rather than a negative case.
- All cases omit preconditions and compress workflows into one step.

Keep this file unchanged. It is evidence of the starting behavior, not an
example of an approved test suite.

## Prompt v1.1 findings

`experiments/password_reset_prompt_v1.1.json` tested additional grounding and
test-design instructions in the system prompt. It corrected the classification
of malformed email input, but regressed or retained more important defects:

- TC-002 still claims that an unregistered address receives a reset link.
- It still invents password rules, expiry values, messages, and timing targets.
- TC-006 adds unsupported load and performance requirements.
- TC-007 invents an ambiguous shared-email scenario and unsafe ownership rules.
- Preconditions remain empty and workflows remain compressed into one step.

Prompt v1.1 is therefore a rejected experiment, not the project default.

## Prompt v1.2 findings

`experiments/password_reset_prompt_v1.2.json` moved a compact completion
checklist after the request data. This fixed the most serious baseline defect:
TC-002 now limits the unregistered-user assertion to the visible confirmation
message and does not claim that the backend sends a link.

The output still fails the full quality bar:

- It invents a 15-minute expiry, password composition rules, and message text.
- Preconditions remain empty.
- TC-006 treats an invalid password as an edge case instead of a negative case.
- Several steps combine setup, action, and verification instead of establishing
  executable test state clearly.

The prompt is a measured improvement, but the experiment shows that prompt
instructions alone cannot enforce factual grounding with this local 4B model.
A separate quality gate or stronger model is required before unattended use.

## Comparison

| Dimension | v1.0 baseline | v1.1 | v1.2 |
| --- | --- | --- | --- |
| Contract validity | Pass | Pass | Pass |
| Requirement coverage | Pass | Pass | Pass |
| Grounding | Fail | Fail | Fail |
| Classification | Fail | Fail | Fail |
| Executability | Fail | Fail | Fail |
| Unregistered-email backend claim | Fail | Fail | Pass |

Runtime observations on this machine:

| Prompt | Input tokens | Output tokens | Total tokens | Duration |
| --- | ---: | ---: | ---: | ---: |
| v1.0 | 722 | 1,142 | 1,864 | 208.7 s |
| v1.1 | 846 | 1,478 | 2,324 | 263.2 s |
| v1.2 | 937 | 1,308 | 2,245 | 219.1 s |

## Model comparison with prompt v1.2

`experiments/password_reset_prompt_v1.2_gemma3_12b.json` applies the same
request, prompt, schema, temperature, and CPU-only runtime to the larger
`gemma3:12b` model. Its companion `_quality.json` file records the deterministic
advisory findings.

Gemma 3 12B improves the result materially:

- It uses the configured expiration period instead of inventing a numeric expiry.
- It classifies invalid password behavior as negative and link expiration as edge.
- It separates workflows into multiple executable actions.
- It keeps the unregistered-email assertion focused on the visible confirmation.

It still does not pass the full rubric:

- All four cases omit explicit preconditions.
- It invents a `Forgot Password` field label.
- It gives unsupported password-policy examples such as missing special characters.
- The functional workflow assumes redirect, persistence, and login behavior not
  stated in the requirements.

| Model | Cases | Advisory findings | Input tokens | Output tokens | Duration |
| --- | ---: | ---: | ---: | ---: | ---: |
| `qwen3:4b-instruct` | 6 | 16 | 937 | 1,308 | 219.1 s |
| `gemma3:12b` | 4 | 7 | 1,002 | 1,075 | 440.8 s |

On this hardware, Gemma cuts the deterministic finding count by more than half
but takes about twice as long. Qwen remains the practical default for iterative
development; Gemma is an optional quality-first comparison model. Neither is
approved for unattended generation without human review.
