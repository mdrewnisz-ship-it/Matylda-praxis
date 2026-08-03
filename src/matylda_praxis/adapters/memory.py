"""Small reference repository with optimistic concurrency."""

from __future__ import annotations

from threading import RLock

from ..domain.models import HypothesisRecord
from ..protocol.errors import ConcurrencyConflict


class InMemoryArtifactRepository:
    def __init__(self) -> None:
        self._records: dict[str, HypothesisRecord] = {}
        self._lock = RLock()

    def get(self, artifact_id: str) -> HypothesisRecord:
        with self._lock:
            try:
                return self._records[artifact_id]
            except KeyError as exc:
                raise KeyError(f"Unknown artifact: {artifact_id}") from exc

    def list(self) -> tuple[HypothesisRecord, ...]:
        with self._lock:
            return tuple(self._records.values())

    def save(self, record: HypothesisRecord, *, expected_revision: int | None) -> None:
        with self._lock:
            current = self._records.get(record.id)
            if current is None:
                if expected_revision is not None:
                    raise ConcurrencyConflict("Artifact does not exist at the expected revision")
            elif expected_revision != current.revision:
                raise ConcurrencyConflict(
                    f"Expected revision {expected_revision}, found {current.revision}"
                )
            self._records[record.id] = record
