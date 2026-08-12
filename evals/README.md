# Local Model Evaluation

This directory preserves representative model outputs so prompt changes can be
compared against the same input instead of judged from memory.

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
