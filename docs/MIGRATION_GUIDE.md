# Selective Migration from Matylda Lab

Praxis imports only the Lab hypothesis registry schema `2`. It does not import
the dashboard, library, logs, generic memory, tensions or room registries.

Migration always requires explicit record IDs. There is no implicit "import
everything" mode.

## Dry run

```bash
PYTHONPATH=src python -m matylda_praxis import-lab \
  /path/to/hypotheses.json \
  --id hyp_first \
  --id hyp_second
```

Without `--apply`, the command parses and validates selected records but does
not write to SQLite.

## Apply

```bash
PYTHONPATH=src python -m matylda_praxis import-lab \
  /path/to/hypotheses.json \
  --id hyp_first \
  --apply
```

The importer preserves IDs, artifact versions, preflight checks, benchmarks,
reviews, deflations, decisions and source events. It adds one
`legacy_record_imported` event containing source provenance.

A record is rejected without a partial write when:

- its human decision was not explicitly confirmed,
- a version sequence is broken,
- benchmark, review, deflation or decision references do not form one chain,
- a working artifact is incomplete,
- review confidence is outside `0..1`,
- a `WAIT`, `REJECT` or `PUBLISH` decision lacks its required fields,
- the source schema is unsupported.

Existing Praxis IDs are skipped, never overwritten.
