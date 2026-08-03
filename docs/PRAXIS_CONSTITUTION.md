# Matylda Praxis Constitution

## Purpose

Matylda Praxis exists to prevent a capable research system from confusing a
coherent narrative with an epistemic result. It expresses that discipline as
typed artifacts, enforced transitions and executable tests.

## Product Boundary

Praxis owns:

- artifact and decision schemas,
- lifecycle invariants,
- deterministic gates,
- hostile-review and deflation contracts,
- evidence lineage and negative memory semantics,
- conformance tests for every execution adapter.

Praxis does not own:

- a general agent loop,
- model hosting or provider selection,
- generic long-term conversational memory,
- search, sandboxing, authentication or synchronization platforms,
- a desktop environment or universal research dashboard.

## First Vertical Slice

Only a versioned hypothesis is a complete artifact type:

```text
SEED -> INCUBATOR -> EXPLORATION -> WORKING
     -> PREFLIGHT -> BENCHMARK -> HOSTILE REVIEW
     -> DEFLATION WHEN REQUIRED -> HUMAN DECISION
```

The allowed decisions are `TEST`, `WAIT`, `REJECT` and `PUBLISH`. Waiting and
rejection are consequences of a decision, not manually assigned folders.

## Non-negotiable Invariants

1. A seed is cheap and does not require review.
2. A working artifact has scope, falsification, next test and exploration cost.
3. A consequential decision references the exact reviewed artifact version and benchmark.
4. A reviewer receives the artifact and benchmark, not the author's private rationale.
5. Broken or incomplete reviewer output fails closed.
6. `REVISE` requires a substantive, versioned deflation.

Hostile-review recommendations use a repairability boundary. `REJECT` is
reserved for a core claim that is already falsified, redundant,
self-sealing/untestable, or cannot be repaired without replacement. `REVISE`
means the artifact can survive through a substantive narrowing, withdrawal of
causal or novelty overclaim, or a more decisive test. `TEST` means the bounded
claim and its proposed next test already survive hostile review. A model's
recommendation informs but never replaces the human decision.
7. Previous artifact versions and decisions are never rewritten.
8. Only an explicit human approval can create `DecisionMemo`.
9. Operational retirement is not recorded as epistemic falsification.
10. Provider adapters must pass the same conformance suite.

## Change Rule

No lifecycle state, artifact type or autonomous subsystem is added without a
repeated failure observed in real protocol runs and a test demonstrating that
the existing model cannot express the case.
