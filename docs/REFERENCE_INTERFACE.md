# Matylda Praxis Reference Interface

The reference interface is intentionally small. It exposes one hypothesis
protocol through a local browser GUI, CLI and JSON API backed by SQLite. It is
not an agent platform or authentication service.

## Run without installation

```bash
PYTHONPATH=src python -m matylda_praxis --help
```

The default database is `.praxis/praxis.db`. Override it with `--db` or the
`MATYLDA_PRAXIS_DB` environment variable.

## CLI lifecycle

Capture and inspect a seed:

```bash
PYTHONPATH=src python -m matylda_praxis create "Pilot effect"
PYTHONPATH=src python -m matylda_praxis list
PYTHONPATH=src python -m matylda_praxis show HYPOTHESIS_ID
```

Advance early states:

```bash
PYTHONPATH=src python -m matylda_praxis advance HYPOTHESIS_ID incubator
PYTHONPATH=src python -m matylda_praxis advance HYPOTHESIS_ID exploration
PYTHONPATH=src python -m matylda_praxis advance HYPOTHESIS_ID working --input artifact.json
```

`artifact.json` uses the fixed hypothesis artifact contract:

```json
{
  "claim": "A bounded pilot effect is measurable.",
  "scope": "One controlled pilot sample.",
  "assumptions": ["The measurement is stable."],
  "evidence_for": ["Pilot observation."],
  "evidence_against": [],
  "falsification_condition": "No effect in the control sample.",
  "next_test": "Run one controlled comparison.",
  "exploration_cost": "30 min"
}
```

The remaining commands are:

```text
preflight HYPOTHESIS_ID
benchmark HYPOTHESIS_ID --input benchmark.json
review HYPOTHESIS_ID --input review.json
deflate HYPOTHESIS_ID --input deflation.json
decide HYPOTHESIS_ID TEST|WAIT|REJECT|PUBLISH --input decision.json
resume HYPOTHESIS_ID --input resume.json
```

The review input contains the fixed hostile-review fields plus the exact
`benchmark_id`. A decision input must contain `rationale`, `operator_id` and
`confirmed_by_human: true`, plus fields required by its decision type.

`resume` requires a recorded `DecisionMemo` and a new evidential basis. Every
decision type can start a linked run, because the outcome of a `TEST`, and
evidence that arrives after `PUBLISH`, are new evidence about the same claim.
The linked run is a separate record; the parent is never rewritten.

Exit codes: `0` success, `2` invalid input or protocol violation, `3` a
concurrent write changed the record before this command could commit. Errors
are printed to stderr as a JSON object, never as a traceback.

## Local GUI and HTTP API

Start the server:

```bash
PYTHONPATH=src python -m matylda_praxis serve --port 8787
```

The default host is `127.0.0.1`. The server has no authentication and must not
be exposed to another network.

Open `http://127.0.0.1:8787/` for the GUI. It provides:

- hypothesis register, search and seed capture,
- state-aware next actions from incubator through human decision,
- working-artifact, preflight, benchmark, DARKROOM and deflation forms,
- explicit human confirmation for `DecisionMemo`,
- evidence-chain and immutable event-history views,
- linked re-entry after any decided run, without rewriting its parent,
- responsive desktop and narrow-window layouts.

The GUI calls the JSON routes below and does not assign state locally. Invalid
or out-of-order actions still fail in the application and domain layers.

Routes:

```text
GET  /health
GET  /hypotheses
POST /hypotheses
GET  /hypotheses/{id}
POST /hypotheses/{id}/advance
POST /hypotheses/{id}/preflight
POST /hypotheses/{id}/benchmark
POST /hypotheses/{id}/review
POST /hypotheses/{id}/deflate
POST /hypotheses/{id}/decision
POST /hypotheses/{id}/resume
```

Both interfaces call the same `ReferenceApplication`; transport code cannot
assign lifecycle state or create a decision outside the domain protocol.

## Local MCP adapter

The optional stdio adapter is installed separately:

```bash
python -m pip install '.[mcp]'
matylda-praxis-mcp --database .praxis/praxis.db
```

It registers nine provider-neutral tools: record inspection, seed capture,
early transitions, preflight, benchmark, hostile review, deflation and
decision proposal. `approve` and `decide` are intentionally absent. The model
cannot supply operator identity, channel or `confirmed_by_human`; a host-only
`ApprovalBoundary` consumes an unexpired, current-revision proposal exactly
once. The adapter opens only stdio and does not add a network listener.
