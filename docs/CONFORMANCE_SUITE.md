# Matylda Praxis Conformance Suite

## Purpose

The conformance suite is an executable form of the Praxis Constitution. A new
model, provider, repository or interface is compatible only when the same
protocol tests pass without weakening assertions.

Run the suite from the Praxis root:

```bash
python -m pytest
```

The suite is deterministic and does not use network access or live model
credits.

## Layers

### Domain contract

`test_protocol.py` and `test_protocol_contract.py` verify:

- bounded lifecycle transitions,
- required working-artifact fields and runtime types,
- duplicate and negative-memory preflight,
- version-specific preflight and benchmark gates,
- exact benchmark-to-review binding,
- fail-closed hostile review,
- substantive deflation and immutable prior versions,
- decision-specific requirements,
- one decision per run,
- state derived from `DecisionMemo`,
- linked re-entry without rewriting the parent,
- separation of epistemic failure from operational retirement.

### Port and adapter contract

`test_ports_and_adapters.py` and `test_adapter_contracts.py` verify:

- OpenAI and Anthropic map to the same domain review,
- author rationale is absent from reviewer input,
- missing, extra or wrongly typed review fields fail closed,
- malformed benchmark output fails closed,
- approval is explicit and attributed,
- stale repository writes lose through optimistic concurrency,
- provider-specific state never enters domain records.

### Adversarial end to end

`test_adversarial_e2e.py` verifies:

- a complete `REVISE -> deflate -> WAIT` evidence chain,
- denied approval leaves no partial decision,
- two concurrent human decisions produce one winner,
- reviewer failure leaves no partial review,
- a benchmark changed during review prevents stale review commit,
- malicious provider fields cannot assign state or decisions,
- serialized records remain provider-neutral.

### Persistence, migration and transport

`test_persistence.py`, `test_migration.py` and
`test_reference_interfaces.py` verify:

- explicit JSON round trips,
- SQLite restart durability and optimistic writes,
- selective dry-run and applied Lab migration,
- rejection of broken historical evidence chains,
- persistence across independent CLI invocations,
- a complete hypothesis run through the reference API,
- transport-level enforcement of human confirmation.

## Provider acceptance rule

A provider adapter is accepted only when it:

1. receives exactly `ReviewRequest`,
2. sends no generator rationale or desired outcome,
3. returns the fixed `HostileReviewDraft` contract,
4. rejects malformed and additional fields,
5. preserves provider exceptions without manufacturing a review,
6. passes the shared adapter and adversarial suites.

Live quality evaluation is a separate benchmark. Passing conformance proves
that an adapter obeys the protocol; it does not prove that the model produces
useful objections.

## Live quality pilot

`benchmarks/darkroom_v1.json` freezes eight deliberately different review
cases. `benchmarks/run_darkroom_eval.py` runs the production adapter without
retrying malformed output and records first-pass contract compliance,
recommendation agreement, objection-concept recall, latency, token use and
estimated cost. The lexical concept score is a transparent smoke metric, not a
semantic quality oracle or a model leaderboard.

Live results are stored under ignored `.praxis/evaluations/`; dated conclusions
belong in `docs/` so raw provider output and operational details do not become
part of the protocol contract. See the
[2026-08-03 DARKROOM report](EVALUATION_REPORT_2026-08-03.md) for the first
Anthropic run and the defects it exposed.

## Current limits

- The first live pilot is small and single-sampled; it measures obvious failure
  modes, not statistical model quality.
- OpenAI live quality remains unmeasured because no API key was available for
  the first pilot.
- SQLite restart durability is tested, but abrupt process termination and
  filesystem corruption recovery are not yet fault-injected.
- The local HTTP transport has no authentication and is intentionally bound to
  loopback by default.
- Semantic duplicate detection remains a future benchmark rather than a
  deterministic contract.
