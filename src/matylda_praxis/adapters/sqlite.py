"""SQLite reference repository with optimistic concurrency."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..domain.models import HypothesisRecord
from ..protocol.errors import ConcurrencyConflict
from .codec import record_from_json, record_to_json


class SQLiteArtifactRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def get(self, artifact_id: str) -> HypothesisRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM artifacts WHERE id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown artifact: {artifact_id}")
        return record_from_json(row[0])

    def list(self) -> tuple[HypothesisRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM artifacts ORDER BY updated_at DESC, id ASC"
            ).fetchall()
        return tuple(record_from_json(row[0]) for row in rows)

    def save(self, record: HypothesisRecord, *, expected_revision: int | None) -> None:
        payload = record_to_json(record)
        with self._connect() as connection:
            if expected_revision is None:
                try:
                    connection.execute(
                        "INSERT INTO artifacts (id, revision, updated_at, payload) VALUES (?, ?, ?, ?)",
                        (record.id, record.revision, record.updated_at, payload),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ConcurrencyConflict(f"Artifact already exists: {record.id}") from exc
                return
            if record.revision != expected_revision + 1:
                raise ConcurrencyConflict(
                    "A repository update must advance the revision exactly once"
                )
            cursor = connection.execute(
                """
                UPDATE artifacts
                SET revision = ?, updated_at = ?, payload = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    record.revision,
                    record.updated_at,
                    payload,
                    record.id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrencyConflict(
                    f"Artifact {record.id} changed before this write could commit"
                )
