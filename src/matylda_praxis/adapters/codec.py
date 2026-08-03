"""Explicit JSON codec for provider-neutral Praxis records."""

from __future__ import annotations

import json
from dataclasses import asdict
from enum import Enum
from typing import Any, Mapping

from ..domain.models import (
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
)
from ..domain.types import (
    DecisionType,
    HypothesisState,
    MemoryClass,
    RejectionReason,
    ReviewRecommendation,
)

SCHEMA_VERSION = 1


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def to_jsonable(value: Any) -> Any:
    """Convert dataclasses already expanded with `asdict` to JSON values."""
    return _json_value(value)


def record_to_dict(record: HypothesisRecord) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "record": _json_value(asdict(record)),
    }


def record_to_json(record: HypothesisRecord) -> str:
    return json.dumps(record_to_dict(record), ensure_ascii=True, sort_keys=True)


def _artifact(raw: Mapping[str, Any]) -> HypothesisArtifact:
    return HypothesisArtifact(
        claim=str(raw.get("claim", "")),
        scope=str(raw.get("scope", "")),
        assumptions=tuple(raw.get("assumptions", ())),
        evidence_for=tuple(raw.get("evidence_for", ())),
        evidence_against=tuple(raw.get("evidence_against", ())),
        falsification_condition=str(raw.get("falsification_condition", "")),
        next_test=str(raw.get("next_test", "")),
        exploration_cost=str(raw.get("exploration_cost", "")),
    )


def _version(raw: Mapping[str, Any]) -> ArtifactVersion:
    return ArtifactVersion(
        number=int(raw["number"]),
        artifact=_artifact(raw["artifact"]),
        reason=str(raw["reason"]),
        created_at=str(raw["created_at"]),
    )


def _preflight(raw: Mapping[str, Any]) -> PreflightCheck:
    return PreflightCheck(
        check_id=str(raw["check_id"]),
        artifact_version=int(raw["artifact_version"]),
        issues=tuple(PreflightIssue(
            code=str(issue["code"]),
            field=str(issue["field"]),
            message=str(issue["message"]),
        ) for issue in raw.get("issues", ())),
        checked_at=str(raw["checked_at"]),
    )


def _benchmark(raw: Mapping[str, Any]) -> BenchmarkResult:
    return BenchmarkResult(
        benchmark_id=str(raw["benchmark_id"]),
        artifact_version=int(raw["artifact_version"]),
        baseline=str(raw["baseline"]),
        sources=tuple(raw["sources"]),
        existing_solution_search=str(raw["existing_solution_search"]),
        result=str(raw["result"]),
        created_at=str(raw["created_at"]),
    )


def _review(raw: Mapping[str, Any]) -> HostileReview:
    return HostileReview(
        strongest_objection=str(raw["strongest_objection"]),
        counterexample=str(raw["counterexample"]),
        hidden_assumptions=tuple(raw.get("hidden_assumptions", ())),
        existing_solution_search=str(raw["existing_solution_search"]),
        falsification_test=str(raw["falsification_test"]),
        minimum_evidence_required=str(raw["minimum_evidence_required"]),
        recommendation=ReviewRecommendation(str(raw["recommendation"])),
        confidence=float(raw["confidence"]),
        review_id=str(raw["review_id"]),
        artifact_version=int(raw["artifact_version"]),
        benchmark_id=str(raw["benchmark_id"]),
        created_at=str(raw["created_at"]),
    )


def _deflation(raw: Mapping[str, Any]) -> DeflationRecord:
    return DeflationRecord(
        deflation_id=str(raw["deflation_id"]),
        review_id=str(raw["review_id"]),
        from_version=int(raw["from_version"]),
        to_version=int(raw["to_version"]),
        changed_fields=tuple(raw.get("changed_fields", ())),
        withdrawn_claims=tuple(raw.get("withdrawn_claims", ())),
        rationale=str(raw["rationale"]),
        created_at=str(raw["created_at"]),
    )


def _decision(raw: Mapping[str, Any]) -> DecisionMemo:
    approval = raw["approval"]
    reason = raw.get("reason_code")
    return DecisionMemo(
        decision_id=str(raw["decision_id"]),
        artifact_version=int(raw["artifact_version"]),
        review_id=str(raw["review_id"]),
        decision=DecisionType(str(raw["decision"])),
        rationale=str(raw["rationale"]),
        approval=ApprovalEvidence(
            operator_id=str(approval["operator_id"]),
            channel=str(approval["channel"]),
            confirmed_at=str(approval["confirmed_at"]),
        ),
        recommendation_seen=ReviewRecommendation(str(raw["recommendation_seen"])),
        reason_code=RejectionReason(str(reason)) if reason else None,
        reentry_condition=raw.get("reentry_condition"),
        review_date=raw.get("review_date"),
        publication_target=raw.get("publication_target"),
        decided_at=str(raw["decided_at"]),
    )


def _memory(raw: Mapping[str, Any]) -> MemoryUpdate:
    return MemoryUpdate(
        memory_id=str(raw["memory_id"]),
        memory_class=MemoryClass(str(raw["memory_class"])),
        reason_code=RejectionReason(str(raw["reason_code"])),
        claim=str(raw["claim"]),
        decision_id=str(raw["decision_id"]),
        created_at=str(raw["created_at"]),
    )


def _event(raw: Mapping[str, Any]) -> ProtocolEvent:
    payload = raw.get("payload", {})
    if not isinstance(payload, Mapping):
        raise ValueError("Event payload must be an object")
    return ProtocolEvent(
        event_id=str(raw["event_id"]),
        kind=str(raw["kind"]),
        artifact_id=str(raw["artifact_id"]),
        payload=dict(payload),
        created_at=str(raw["created_at"]),
    )


def record_from_dict(payload: Mapping[str, Any]) -> HypothesisRecord:
    if set(payload) != {"schema_version", "record"}:
        raise ValueError("Praxis payload does not match the fixed envelope")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"Unsupported Praxis schema: {payload['schema_version']}")
    raw = payload["record"]
    if not isinstance(raw, Mapping):
        raise ValueError("Praxis record must be an object")
    versions = tuple(_version(item) for item in raw.get("versions", ()))
    if not versions:
        raise ValueError("Praxis record requires at least one version")
    return HypothesisRecord(
        id=str(raw["id"]),
        title=str(raw["title"]),
        state=HypothesisState(str(raw["state"])),
        versions=versions,
        preflight_checks=tuple(_preflight(item) for item in raw.get("preflight_checks", ())),
        benchmark_results=tuple(_benchmark(item) for item in raw.get("benchmark_results", ())),
        hostile_reviews=tuple(_review(item) for item in raw.get("hostile_reviews", ())),
        deflations=tuple(_deflation(item) for item in raw.get("deflations", ())),
        decision_memos=tuple(_decision(item) for item in raw.get("decision_memos", ())),
        memory_updates=tuple(_memory(item) for item in raw.get("memory_updates", ())),
        events=tuple(_event(item) for item in raw.get("events", ())),
        parent_id=raw.get("parent_id"),
        revision=int(raw.get("revision", 0)),
        created_at=str(raw["created_at"]),
        updated_at=str(raw["updated_at"]),
    )


def record_from_json(payload: str) -> HypothesisRecord:
    raw = json.loads(payload)
    if not isinstance(raw, Mapping):
        raise ValueError("Praxis payload must be a JSON object")
    return record_from_dict(raw)
