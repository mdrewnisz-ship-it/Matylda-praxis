from __future__ import annotations

from dataclasses import replace

import pytest

from matylda_praxis.adapters.codec import record_from_dict, record_from_json, record_to_json
from matylda_praxis.adapters.sqlite import SQLiteArtifactRepository
from matylda_praxis.domain.models import ApprovalEvidence, HypothesisRecord
from matylda_praxis.domain.types import DecisionType
from matylda_praxis.protocol.errors import ConcurrencyConflict
from matylda_praxis.protocol.lifecycle import decide


def test_codec_round_trips_a_complete_decided_record(reviewed_factory):
    reviewed, _, _ = reviewed_factory()
    decided, _ = decide(
        reviewed,
        DecisionType.WAIT,
        "Wait for replication.",
        ApprovalEvidence("codec-operator", "codec-test"),
        reentry_condition="Replication available.",
        review_date="2026-10-01",
    )

    restored = record_from_json(record_to_json(decided))

    assert restored == decided
    assert restored.effective_state == decided.effective_state


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema_version": 999, "record": {}},
        {"schema_version": 1, "record": {}},
        {"schema_version": 1, "record": {}, "provider": "openai"},
    ],
)
def test_codec_rejects_unknown_or_incomplete_envelopes(payload):
    with pytest.raises((KeyError, ValueError)):
        record_from_dict(payload)


def test_sqlite_repository_persists_across_instances(tmp_path):
    path = tmp_path / "praxis.db"
    first = SQLiteArtifactRepository(path)
    record = HypothesisRecord.seed("Persistent record")
    first.save(record, expected_revision=None)

    second = SQLiteArtifactRepository(path)

    assert second.get(record.id) == record
    assert second.list() == (record,)


def test_sqlite_repository_rejects_duplicate_and_stale_writes(tmp_path):
    repository = SQLiteArtifactRepository(tmp_path / "praxis.db")
    record = HypothesisRecord.seed("Concurrent persistent record")
    repository.save(record, expected_revision=None)

    with pytest.raises(ConcurrencyConflict, match="already exists"):
        repository.save(record, expected_revision=None)

    changed = replace(record, title="Changed", revision=record.revision + 1)
    repository.save(changed, expected_revision=record.revision)

    stale = replace(record, title="Stale", revision=record.revision + 1)
    with pytest.raises(ConcurrencyConflict, match="changed"):
        repository.save(stale, expected_revision=record.revision)
