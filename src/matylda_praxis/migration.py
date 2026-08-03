"""Selective, fail-closed import of Matylda Lab hypothesis registries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .domain.models import (
    ApprovalEvidence,
    ArtifactVersion,
    BenchmarkResult,
    DecisionMemo,
    DeflationRecord,
    HostileReview,
    HypothesisArtifact,
    HypothesisRecord,
    MemoryUpdate,
    PreflightCheck,
    PreflightIssue,
    ProtocolEvent,
    new_id,
    utc_now,
)
from .domain.types import (
    DecisionType,
    EPISTEMIC_NEGATIVE_REASONS,
    HypothesisState,
    MemoryClass,
    RejectionReason,
    ReviewRecommendation,
)
from .ports.interfaces import ArtifactRepository
from .protocol.errors import ConcurrencyConflict
from .protocol.preflight import artifact_issues

LEGACY_STATES = {
    "seed": HypothesisState.SEED,
    "incubator": HypothesisState.INCUBATOR,
    "exploration": HypothesisState.EXPLORATION,
    "working_model": HypothesisState.WORKING,
    "working": HypothesisState.WORKING,
    "waiting_room": HypothesisState.WAITING,
    "waiting": HypothesisState.WAITING,
    "cemetery": HypothesisState.CEMETERY,
}


@dataclass(frozen=True, slots=True)
class MigrationFailure:
    record_id: str
    error: str


@dataclass(frozen=True, slots=True)
class MigrationReport:
    source: str
    selected: tuple[str, ...]
    ready: tuple[str, ...]
    imported: tuple[str, ...]
    skipped: tuple[str, ...]
    failures: tuple[MigrationFailure, ...]
    dry_run: bool

    @property
    def ok(self) -> bool:
        return not self.failures


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _required_text(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"legacy field {key} is required text")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("legacy optional text has an invalid type")
    return value.strip() or None


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())


def _legacy_artifact(raw: Mapping[str, Any]) -> HypothesisArtifact:
    return HypothesisArtifact(
        claim=str(raw.get("claim", "")),
        scope=str(raw.get("scope", "")),
        assumptions=_strings(raw.get("assumptions", []), "assumptions"),
        evidence_for=_strings(raw.get("evidence_for", []), "evidence_for"),
        evidence_against=_strings(raw.get("evidence_against", []), "evidence_against"),
        falsification_condition=str(raw.get("falsification_condition", "")),
        next_test=str(raw.get("next_test", "")),
        exploration_cost=str(raw.get("exploration_cost", "")),
    )


def _versions(raw: Mapping[str, Any], created_at: str) -> tuple[ArtifactVersion, ...]:
    source_versions = raw.get("versions")
    if not source_versions:
        return (ArtifactVersion(1, _legacy_artifact(raw), "legacy_import", created_at),)
    if not isinstance(source_versions, list):
        raise ValueError("legacy versions must be a list")
    result = []
    for item in source_versions:
        item = _mapping(item, "legacy version")
        artifact = _mapping(item.get("artifact"), "legacy version artifact")
        result.append(ArtifactVersion(
            number=int(item["version"]),
            artifact=_legacy_artifact(artifact),
            reason=_required_text(item, "reason"),
            created_at=_required_text(item, "created_at"),
        ))
    if [item.number for item in result] != list(range(1, len(result) + 1)):
        raise ValueError("legacy versions are not a continuous sequence")
    return tuple(result)


def _preflights(raw: Mapping[str, Any]) -> tuple[PreflightCheck, ...]:
    result = []
    for item in raw.get("preflight_checks", []):
        item = _mapping(item, "legacy preflight")
        issues = []
        for issue in item.get("issues", []):
            issue = _mapping(issue, "legacy preflight issue")
            issues.append(PreflightIssue(
                code=_required_text(issue, "code").casefold(),
                field=_required_text(issue, "field"),
                message=_required_text(issue, "message"),
            ))
        passed = item.get("passed")
        if passed is not (not issues):
            raise ValueError("legacy preflight passed flag contradicts its issues")
        result.append(PreflightCheck(
            check_id=_required_text(item, "check_id"),
            artifact_version=int(item["artifact_version"]),
            issues=tuple(issues),
            checked_at=_required_text(item, "checked_at"),
        ))
    return tuple(result)


def _benchmarks(raw: Mapping[str, Any]) -> tuple[BenchmarkResult, ...]:
    result = []
    for item in raw.get("benchmark_results", []):
        item = _mapping(item, "legacy benchmark")
        result.append(BenchmarkResult(
            benchmark_id=_required_text(item, "benchmark_id"),
            artifact_version=int(item["artifact_version"]),
            baseline=_required_text(item, "baseline"),
            sources=_strings(item.get("sources"), "benchmark sources"),
            existing_solution_search=_required_text(item, "existing_solution_search"),
            result=_required_text(item, "result"),
            created_at=_required_text(item, "created_at"),
        ))
    return tuple(result)


def _reviews(raw: Mapping[str, Any]) -> tuple[HostileReview, ...]:
    result = []
    for item in raw.get("hostile_reviews", []):
        item = _mapping(item, "legacy hostile review")
        result.append(HostileReview(
            strongest_objection=_required_text(item, "strongest_objection"),
            counterexample=_required_text(item, "counterexample"),
            hidden_assumptions=_strings(item.get("hidden_assumptions", []), "hidden assumptions"),
            existing_solution_search=_required_text(item, "existing_solution_search"),
            falsification_test=_required_text(item, "falsification_test"),
            minimum_evidence_required=_required_text(item, "minimum_evidence_required"),
            recommendation=ReviewRecommendation(_required_text(item, "recommendation").upper()),
            confidence=float(item["confidence"]),
            review_id=_required_text(item, "review_id"),
            artifact_version=int(item["artifact_version"]),
            benchmark_id=_required_text(item, "benchmark_id"),
            created_at=_required_text(item, "created_at"),
        ))
    return tuple(result)


def _deflations(raw: Mapping[str, Any]) -> tuple[DeflationRecord, ...]:
    result = []
    for item in raw.get("deflations", []):
        item = _mapping(item, "legacy deflation")
        diff = _mapping(item.get("diff", {}), "legacy deflation diff")
        result.append(DeflationRecord(
            deflation_id=_required_text(item, "deflation_id"),
            review_id=_required_text(item, "review_id"),
            from_version=int(item["from_version"]),
            to_version=int(item["to_version"]),
            changed_fields=tuple(str(key) for key in diff),
            withdrawn_claims=_strings(item.get("withdrawn_claims", []), "withdrawn claims"),
            rationale=_required_text(item, "rationale"),
            created_at=_required_text(item, "created_at"),
        ))
    return tuple(result)


def _decisions_and_memory(
    raw: Mapping[str, Any],
    reviews: tuple[HostileReview, ...],
    claim: str,
) -> tuple[tuple[DecisionMemo, ...], tuple[MemoryUpdate, ...]]:
    review_by_id = {item.review_id: item for item in reviews}
    decisions = []
    memory = []
    for item in raw.get("decision_memos", []):
        item = _mapping(item, "legacy decision")
        if item.get("human_confirmed") is not True:
            raise ValueError("legacy decision has no explicit human confirmation")
        review_id = _required_text(item, "review_id")
        review = review_by_id.get(review_id)
        if review is None:
            raise ValueError("legacy decision references an unknown review")
        decision_type = DecisionType(_required_text(item, "decision").upper())
        reason_raw = _optional_text(item.get("reason_code"))
        reason = RejectionReason(reason_raw.upper()) if reason_raw else None
        decided_at = _required_text(item, "decided_at")
        memo = DecisionMemo(
            decision_id=_required_text(item, "decision_id"),
            artifact_version=int(item["artifact_version"]),
            review_id=review_id,
            decision=decision_type,
            rationale=_required_text(item, "rationale"),
            approval=ApprovalEvidence(
                operator_id=_required_text(item, "decided_by"),
                channel="legacy_import",
                confirmed_at=decided_at,
            ),
            recommendation_seen=review.recommendation,
            reason_code=reason,
            reentry_condition=_optional_text(item.get("reentry_condition")),
            review_date=_optional_text(item.get("review_date")),
            publication_target=_optional_text(item.get("publication_target")),
            decided_at=decided_at,
        )
        if decision_type is DecisionType.WAIT and not (
            memo.reentry_condition and memo.review_date
        ):
            raise ValueError("legacy WAIT decision lacks re-entry condition or review date")
        if decision_type is DecisionType.PUBLISH and not memo.publication_target:
            raise ValueError("legacy PUBLISH decision lacks publication target")
        decisions.append(memo)
        if decision_type is DecisionType.REJECT:
            if reason is None:
                raise ValueError("legacy REJECT decision has no typed reason")
            memory_class = (
                MemoryClass.EPISTEMIC_NEGATIVE
                if reason in EPISTEMIC_NEGATIVE_REASONS
                else MemoryClass.OPERATIONAL_RETIREMENT
            )
            memory.append(MemoryUpdate(
                memory_id=new_id("memory"),
                memory_class=memory_class,
                reason_code=reason,
                claim=claim,
                decision_id=memo.decision_id,
                created_at=decided_at,
            ))
    if len(decisions) > 1:
        raise ValueError("legacy run contains more than one DecisionMemo")
    return tuple(decisions), tuple(memory)


def _validate_converted(record: HypothesisRecord) -> None:
    version_numbers = {item.number for item in record.versions}
    if record.effective_state in {
        HypothesisState.WORKING,
        HypothesisState.WAITING,
        HypothesisState.CEMETERY,
    }:
        issues = artifact_issues(record.artifact)
        if issues:
            raise ValueError(
                "legacy working artifact is incomplete: "
                + ", ".join(item.field for item in issues)
            )
    for check in record.preflight_checks:
        if check.artifact_version not in version_numbers:
            raise ValueError("legacy preflight references an unknown artifact version")
    benchmarks = {item.benchmark_id: item for item in record.benchmark_results}
    for benchmark in benchmarks.values():
        if benchmark.artifact_version not in version_numbers or not benchmark.sources:
            raise ValueError("legacy benchmark is incomplete or references an unknown version")
    reviews = {item.review_id: item for item in record.hostile_reviews}
    for review in reviews.values():
        benchmark = benchmarks.get(review.benchmark_id)
        if benchmark is None or benchmark.artifact_version != review.artifact_version:
            raise ValueError("legacy review is not bound to its exact benchmark")
        if not 0 <= review.confidence <= 1:
            raise ValueError("legacy review confidence is outside 0..1")
    for item in record.deflations:
        if (
            item.review_id not in reviews
            or item.from_version not in version_numbers
            or item.to_version not in version_numbers
        ):
            raise ValueError("legacy deflation has a broken evidence reference")
    for memo in record.decision_memos:
        review = reviews.get(memo.review_id)
        if review is None or memo.artifact_version not in version_numbers:
            raise ValueError("legacy decision has a broken review or version reference")
        if review.artifact_version != memo.artifact_version and not any(
            item.review_id == review.review_id and item.to_version == memo.artifact_version
            for item in record.deflations
        ):
            raise ValueError("legacy decision is not linked to review through deflation")
    event_ids = [item.event_id for item in record.events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("legacy record contains duplicate event IDs")


def convert_legacy_record(
    raw: Mapping[str, Any],
    registry_events: list[Mapping[str, Any]],
    *,
    source: str,
) -> HypothesisRecord:
    record_id = _required_text(raw, "id")
    title = _required_text(raw, "title")
    created_at = _required_text(raw, "created_at")
    updated_at = _required_text(raw, "updated_at")
    state_raw = _required_text(raw, "state")
    try:
        state = LEGACY_STATES[state_raw]
    except KeyError as exc:
        raise ValueError(f"unsupported legacy state: {state_raw}") from exc
    versions = _versions(raw, created_at)
    reviews = _reviews(raw)
    decisions, memory = _decisions_and_memory(raw, reviews, versions[-1].artifact.claim)
    events = []
    for item in registry_events:
        if item.get("record_id") != record_id:
            continue
        payload = item.get("payload", {})
        if not isinstance(payload, Mapping):
            raise ValueError("legacy event payload must be an object")
        events.append(ProtocolEvent(
            event_id=_required_text(item, "event_id"),
            kind=_required_text(item, "event_type"),
            artifact_id=record_id,
            payload=dict(payload),
            created_at=_required_text(item, "created_at"),
        ))
    events.append(ProtocolEvent(
        event_id=new_id("evt"),
        kind="legacy_record_imported",
        artifact_id=record_id,
        payload={"source": source, "source_schema": 2},
    ))
    converted = HypothesisRecord(
        id=record_id,
        title=title,
        state=state,
        versions=versions,
        preflight_checks=_preflights(raw),
        benchmark_results=_benchmarks(raw),
        hostile_reviews=reviews,
        deflations=_deflations(raw),
        decision_memos=decisions,
        memory_updates=memory,
        events=tuple(events),
        parent_id=_optional_text(raw.get("parent_id")),
        revision=len(events),
        created_at=created_at,
        updated_at=updated_at,
    )
    _validate_converted(converted)
    return converted


def migrate_legacy_registry(
    source: str | Path,
    repository: ArtifactRepository,
    selected_ids: list[str] | tuple[str, ...],
    *,
    dry_run: bool = True,
) -> MigrationReport:
    path = Path(source).expanduser()
    selected = tuple(dict.fromkeys(item.strip() for item in selected_ids if item.strip()))
    if not selected:
        raise ValueError("Selective migration requires at least one explicit record ID")
    raw_registry = json.loads(path.read_text(encoding="utf-8"))
    registry = _mapping(raw_registry, "legacy registry")
    if registry.get("schema_version") != 2:
        raise ValueError("Only Matylda Lab hypothesis registry schema 2 is supported")
    records = registry.get("records")
    events = registry.get("events", [])
    if not isinstance(records, list) or not isinstance(events, list):
        raise ValueError("Legacy registry records and events must be lists")
    by_id = {
        str(item.get("id")): item
        for item in records
        if isinstance(item, Mapping) and item.get("id")
    }
    ready = []
    imported = []
    skipped = []
    failures = []
    for record_id in selected:
        raw = by_id.get(record_id)
        if raw is None:
            failures.append(MigrationFailure(record_id, "record not found in source registry"))
            continue
        try:
            converted = convert_legacy_record(
                raw,
                [item for item in events if isinstance(item, Mapping)],
                source=str(path),
            )
            try:
                repository.get(record_id)
            except KeyError:
                pass
            else:
                skipped.append(record_id)
                continue
            ready.append(record_id)
            if not dry_run:
                repository.save(converted, expected_revision=None)
                imported.append(record_id)
        except (KeyError, TypeError, ValueError, ConcurrencyConflict) as exc:
            failures.append(MigrationFailure(record_id, str(exc)))
    return MigrationReport(
        source=str(path),
        selected=selected,
        ready=tuple(ready),
        imported=tuple(imported),
        skipped=tuple(skipped),
        failures=tuple(failures),
        dry_run=dry_run,
    )
