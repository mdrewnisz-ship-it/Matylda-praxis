# Matylda Praxis Migration Manifest

## Provenance

- Source implementation: `/Users/michaldrewnisz/matylda lite`
- Praxis copy created before: 2026-08-03
- Migration baseline recorded: 2026-08-03
- Strategy: extract protocol contracts; do not rename the complete application

The source Matylda Lab directory is the frozen reference. No Praxis migration
step may modify it.

## Baseline fingerprints

```text
ba7485d08868853a4437d088f87d9efd57429bf185945ae82d196c6edc86d933  docs/MATYLDA_LAB_CHARTER.md
64618618f5b300c242f20955142b2337451dedb1ade0614d0dd89bab4d25c1c8  docs/ARCHITECTURE_E2E_REPORT_2026-08-01.md
7614ec50a9fe690a537595d0fb9257c3c3baaa3d080f37147db54f142d1a5f3a  src/matylda_lite/hypothesis_manager.py
ed2a9ad38d7b37c932fd4c797300142647bc7f18322ef2b220e1ef9a2832f445  src/matylda_lite/atomic_state.py
e6b0b7008e72e9b5f2e0979f8e1cb9f16003959bcd14f6328eaa82c107e8bceb  tests/test_hypothesis_manager.py
416b00fb4bff205e81a4ae20ca02f91c14d71fad46c33dbda58c9c473cfee6f3  tests/test_hypothesis_architecture_e2e.py
```

These hashes identify the migration inputs. New Praxis modules do not import
the legacy package.

## Retained as methodology

- versioned `HypothesisRecord`,
- deterministic preflight,
- benchmark evidence contract,
- isolated hostile review with a fixed output contract,
- explicit deflation and preserved prior versions,
- one human `DecisionMemo`,
- typed negative memory and re-entry lineage,
- adversarial contract and end-to-end tests.

## Excluded from the Praxis product

- desktop application bundle and dashboard,
- OCR, browser automation and generic research utilities,
- silos, Sleeping Matylda and homeostasis,
- operational logs, queues and telemetry history,
- private library, attachments and research memory,
- generated artifacts, caches and local environment files,
- legacy JSON storage as a required domain dependency.

Excluded material is not deleted during extraction. It remains in the copied
folder as ignored migration input and in the frozen source Lab directory.
