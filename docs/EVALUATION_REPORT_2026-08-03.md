# DARKROOM Live Evaluation - 2026-08-03

## Decision

Keep the current Praxis artifact type, lifecycle and reference interface. Do
not add another room, artifact type or agent based on this pilot.

The useful changes were confined to the Anthropic transport contract and the
meaning of the existing `REJECT`, `REVISE` and `TEST` recommendations:

- Anthropic now receives a strict output schema compatible with its supported
  JSON Schema subset; the shared parser still enforces the full contract.
- DARKROOM output is explicitly concise so the default 1,600-token budget is
  sufficient for complex reviews.
- `REJECT` is reserved for an irreparable core claim; repairable overclaim is
  sent to `REVISE` and versioned deflation.

## Method

The frozen `benchmarks/darkroom_v1.json` suite contains eight cases selected
before the final run. It covers a bounded signal, post-hoc generalization,
self-sealing unfalsifiability, renamed prior art, causal confounding, an
expensive discriminating test, a coherent story contradicted by direct data,
and a resource-limited but epistemically live hypothesis.

Each first-pass result records:

- strict contract validity with no retry,
- agreement with a predeclared set of acceptable recommendations,
- lexical recall of predeclared objection concepts,
- input/output tokens, latency and estimated token cost.

Concept recall is a transparent smoke metric, not a semantic judge. The pilot
uses one sample per case and cannot establish statistical model reliability.

## Provider And Price

The final run used `claude-sonnet-5` with a 1,600-token output cap. Cost was
estimated at the introductory standard price in force on 2026-08-03: USD 2 per
million input tokens and USD 10 per million output tokens. Anthropic documents
the model ID and the introductory price through 2026-08-31 in its
[models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
and [pricing page](https://platform.claude.com/docs/en/about-claude/pricing).

OpenAI was not run because `OPENAI_API_KEY` was absent. The OpenAI adapter and
evaluation path remain available, but this report makes no cross-provider
quality claim.

## Defects Found During The Series

1. The original Anthropic call named no output schema. The model produced a
   sensible objection in its own three-field shape, and the fail-closed parser
   correctly rejected it.
2. Anthropic rejected the shared schema because its Structured Outputs subset
   does not accept numeric `minimum`/`maximum`. Removing those two transport
   keywords while retaining parser validation fixed interoperability without
   weakening the domain contract.
3. Two reviews were truncated at the evaluation tool's initial 1,200-token
   cap. One still truncated at the production 1,600-token cap. A concise-output
   requirement reduced the difficult case to 694 output tokens without
   increasing the cap.
4. Before recommendation calibration, a repairable confounded causal claim was
   marked `REJECT`. Defining the repairability boundary changed it to `REVISE`
   while leaving self-sealing and directly falsified claims at `REJECT`.

## Final Run

| Metric | Result |
|---|---:|
| Contract validity | 8/8 (100%) |
| Acceptable recommendation | 8/8 (100%) |
| Mean objection-concept recall | 83.3% |
| Input tokens | 9,009 |
| Output tokens | 4,815 |
| Mean latency | 8.53 s |
| Estimated final-run cost | USD 0.066168 |

| Case | Recommendation | Concept recall |
|---|---|---:|
| bounded-signal | REVISE | 2/2 |
| post-hoc-subgroup | REVISE | 2/3 |
| unfalsifiable-flexibility | REJECT | 1/2 |
| known-solution-renamed | REVISE | 2/2 |
| confounded-observation | REVISE | 2/2 |
| expensive-discrimination | REVISE | 1/2 |
| contradicted-coherent-story | REJECT | 2/2 |
| resource-limit-not-false | REVISE | 2/2 |

Across all diagnostic, repair and regression calls, 31 case executions cost an
estimated USD 0.263388. A rejected preflight request consumed no tokens and is
included in the execution count.

## Interpretation

The final behavior is critical without being uniformly terminal. DARKROOM
preserved `REJECT` for a self-sealing claim and a claim already contradicted by
its direct measurement. It used `REVISE` for false novelty, causal confounding,
insufficient test power and resource constraints. This is the intended Praxis
boundary: criticism may be strong while disposition remains proportional.

The main remaining uncertainty is stochastic stability. The next justified
measurement is repeated sampling of the same frozen suite, then a provider
comparison when an OpenAI API key is available. Neither requires a new domain
object or UI. New benchmark cases should be added only when real Praxis runs
expose a failure not represented here.
