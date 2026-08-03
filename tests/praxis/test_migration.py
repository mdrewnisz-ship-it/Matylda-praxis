from __future__ import annotations

import json

import pytest

from matylda_praxis.adapters.sqlite import SQLiteArtifactRepository
from matylda_praxis.domain.types import DecisionType, HypothesisState
from matylda_praxis.migration import migrate_legacy_registry


STAMP = "2026-08-01T12:00:00+00:00"


def legacy_record(record_id: str, title: str, *, decided: bool = False):
    artifact = {
        "claim": f"{title} has a measurable effect.",
        "scope": "One pilot sample.",
        "assumptions": ["Measurement is stable."],
        "evidence_for": ["Pilot observation."],
        "evidence_against": [],
        "falsification_condition": "No effect in control.",
        "next_test": "Controlled comparison.",
        "exploration_cost": "30 min",
    }
    record = {
        "id": record_id,
        "title": title,
        "state": "waiting_room" if decided else "working_model",
        "created_at": STAMP,
        "updated_at": STAMP,
        "parent_id": None,
        "versions": [{
            "version": 1,
            "created_at": STAMP,
            "reason": "created",
            "artifact": artifact,
        }],
        "preflight_checks": [{
            "check_id": f"pre-{record_id}",
            "artifact_version": 1,
            "checked_at": STAMP,
            "passed": True,
            "issues": [],
        }],
        "benchmark_results": [{
            "benchmark_id": f"bench-{record_id}",
            "artifact_version": 1,
            "baseline": "Null model.",
            "sources": ["source:legacy"],
            "existing_solution_search": "Index checked.",
            "result": "No equivalent result.",
            "created_at": STAMP,
        }],
        "hostile_reviews": [{
            "review_id": f"review-{record_id}",
            "artifact_version": 1,
            "benchmark_id": f"bench-{record_id}",
            "strongest_objection": "Selection bias.",
            "counterexample": "Randomized sample has no effect.",
            "hidden_assumptions": ["Representative sample."],
            "existing_solution_search": "Adjacent term checked.",
            "falsification_test": "Randomize assignment.",
            "minimum_evidence_required": "One replication.",
            "recommendation": "TEST",
            "confidence": 0.72,
            "created_at": STAMP,
        }],
        "deflations": [],
        "decision_memos": [],
    }
    if decided:
        record["decision_memos"] = [{
            "decision_id": f"decision-{record_id}",
            "artifact_version": 1,
            "review_id": f"review-{record_id}",
            "decision": "WAIT",
            "rationale": "Wait for replication.",
            "decided_by": "legacy-operator",
            "human_confirmed": True,
            "decided_at": STAMP,
            "reason_code": None,
            "reentry_condition": "Replication available.",
            "review_date": "2026-10-01",
            "publication_target": None,
        }]
    return record


def write_registry(path, records):
    events = [{
        "event_id": f"evt-{record['id']}",
        "record_id": record["id"],
        "event_type": "artifact_created",
        "created_at": STAMP,
        "payload": {"version": 1},
    } for record in records]
    path.write_text(json.dumps({
        "schema_version": 2,
        "records": records,
        "events": events,
    }), encoding="utf-8")


def test_migration_is_selective_and_dry_run_writes_nothing(tmp_path):
    source = tmp_path / "legacy.json"
    write_registry(source, [
        legacy_record("hyp-a", "Selected"),
        legacy_record("hyp-b", "Not selected"),
    ])
    repository = SQLiteArtifactRepository(tmp_path / "praxis.db")

    report = migrate_legacy_registry(source, repository, ["hyp-a"], dry_run=True)

    assert report.ok
    assert report.ready == ("hyp-a",)
    assert report.imported == ()
    assert repository.list() == ()


def test_migration_preserves_selected_decision_lineage(tmp_path):
    source = tmp_path / "legacy.json"
    write_registry(source, [legacy_record("hyp-wait", "Waiting", decided=True)])
    repository = SQLiteArtifactRepository(tmp_path / "praxis.db")

    report = migrate_legacy_registry(source, repository, ["hyp-wait"], dry_run=False)
    restored = repository.get("hyp-wait")

    assert report.imported == ("hyp-wait",)
    assert restored.disposition is DecisionType.WAIT
    assert restored.effective_state is HypothesisState.WAITING
    assert restored.decision_memos[0].approval.operator_id == "legacy-operator"
    assert restored.decision_memos[0].approval.channel == "legacy_import"
    assert restored.events[-1].kind == "legacy_record_imported"


def test_migration_reports_missing_and_unsafe_records_without_partial_write(tmp_path):
    source = tmp_path / "legacy.json"
    unsafe = legacy_record("hyp-unsafe", "Unsafe", decided=True)
    unsafe["decision_memos"][0]["human_confirmed"] = False
    write_registry(source, [unsafe])
    repository = SQLiteArtifactRepository(tmp_path / "praxis.db")

    report = migrate_legacy_registry(
        source,
        repository,
        ["hyp-unsafe", "hyp-missing"],
        dry_run=False,
    )

    assert not report.ok
    assert {failure.record_id for failure in report.failures} == {
        "hyp-unsafe", "hyp-missing",
    }
    assert repository.list() == ()


def test_migration_requires_explicit_selection(tmp_path):
    source = tmp_path / "legacy.json"
    write_registry(source, [legacy_record("hyp-a", "Selected")])
    repository = SQLiteArtifactRepository(tmp_path / "praxis.db")

    with pytest.raises(ValueError, match="explicit record ID"):
        migrate_legacy_registry(source, repository, [], dry_run=True)


def test_repeated_import_skips_existing_record(tmp_path):
    source = tmp_path / "legacy.json"
    write_registry(source, [legacy_record("hyp-a", "Selected")])
    repository = SQLiteArtifactRepository(tmp_path / "praxis.db")

    migrate_legacy_registry(source, repository, ["hyp-a"], dry_run=False)
    repeated = migrate_legacy_registry(source, repository, ["hyp-a"], dry_run=False)

    assert repeated.skipped == ("hyp-a",)
    assert repeated.imported == ()


@pytest.mark.parametrize(
    "damage",
    [
        lambda record: record["hostile_reviews"][0].update({"benchmark_id": "missing"}),
        lambda record: record["hostile_reviews"][0].update({"confidence": 1.5}),
        lambda record: record["decision_memos"][0].update({"review_date": None}),
    ],
)
def test_migration_rejects_broken_evidence_lineage(tmp_path, damage):
    source = tmp_path / "legacy.json"
    broken = legacy_record("hyp-broken", "Broken", decided=True)
    damage(broken)
    write_registry(source, [broken])
    repository = SQLiteArtifactRepository(tmp_path / "praxis.db")

    report = migrate_legacy_registry(source, repository, ["hyp-broken"], dry_run=False)

    assert not report.ok
    assert report.imported == ()
    assert repository.list() == ()
