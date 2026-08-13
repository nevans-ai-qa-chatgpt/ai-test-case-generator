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
