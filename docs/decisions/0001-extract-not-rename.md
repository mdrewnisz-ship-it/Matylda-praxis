# ADR 0001: Extract the Protocol Instead of Renaming Lab

Status: accepted

## Context

The initial Praxis directory is a complete Matylda Lab copy, including runtime
data, UI, research utilities and historical subsystems. A global rename would
preserve the platform coupling and maintenance burden.

## Decision

New code is written under `matylda_praxis`. The legacy `matylda_lite` package
is migration input only and is excluded from the Praxis repository. Domain
code depends on ports; provider, storage and interface integrations implement
those ports as adapters.

## Consequences

- Lab remains reproducible and untouched.
- Praxis starts with one small vertical slice.
- Existing behavior is carried over through contracts and tests, not imports.
- Features outside the product boundary require a new decision record.
