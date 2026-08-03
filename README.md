# Matylda Praxis

Matylda Praxis is a portable, executable epistemic protocol. It governs how a
research artifact moves from an inexpensive observation to a versioned claim,
benchmark, hostile review, deflation and explicit human decision.

Praxis is not an agent platform. Models, storage engines, search systems and
user interfaces are replaceable adapters around the protocol.

The copied Matylda Lab implementation remains in this directory only as
migration input and is excluded from the Praxis repository. New work belongs
under `src/matylda_praxis`, `tests/praxis`, `benchmarks` and `docs`.

See [Praxis Constitution](docs/PRAXIS_CONSTITUTION.md) and
[Migration Manifest](docs/MIGRATION_MANIFEST.md). Compatibility requirements
are defined by the [Conformance Suite](docs/CONFORMANCE_SUITE.md).
The first live provider findings are recorded in the
[DARKROOM evaluation report](docs/EVALUATION_REPORT_2026-08-03.md).

The runnable surface is documented in the
[Reference Interface](docs/REFERENCE_INTERFACE.md). Importing selected Lab
records is covered by the [Migration Guide](docs/MIGRATION_GUIDE.md).

## Development

Run the Praxis conformance suite:

```bash
python -m pytest
```

Run the CLI directly from a checkout:

```bash
PYTHONPATH=src python -m matylda_praxis --help
```

Run the frozen live DARKROOM pilot with explicit current token prices:

```bash
python benchmarks/run_darkroom_eval.py \
  --provider anthropic \
  --model claude-sonnet-5 \
  --input-price 2 \
  --output-price 10 \
  --output .praxis/evaluations/anthropic-sonnet-5.json
```

Live evaluation spends provider credits and is intentionally separate from the
deterministic conformance suite. Pricing is supplied at invocation time so a
stale rate cannot silently enter the measurement.

Legacy Lab tests are retained locally as migration evidence but ignored by the
Praxis repository and are not part of its default test run.
