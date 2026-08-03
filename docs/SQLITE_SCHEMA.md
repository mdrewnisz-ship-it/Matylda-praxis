# SQLite persistence contract

Matylda Praxis uses SQLite only as a reference persistence adapter. The portable
contract remains the versioned JSON envelope from `adapters.codec`.

## Current schema

- SQLite `user_version`: `1`
- table: `artifacts`
- primary key: artifact id
- optimistic lock: integer revision
- durable mode: WAL with `synchronous=FULL`

Opening a database with a newer `user_version` fails without modifying it.
Version `0` databases created by Praxis 0.1 are upgraded in place to version `1`;
the table and payload are unchanged.

## Recovery policy

Committed writes must survive process termination. Uncommitted transactions are
rolled back by SQLite. Operators can call `integrity_check()` and a passive WAL
`checkpoint()`; the adapter does not attempt destructive automatic repair.

Future migrations must be explicit, forward-only functions covered by a fixture
from every supported prior schema. Back up the database before migration.
