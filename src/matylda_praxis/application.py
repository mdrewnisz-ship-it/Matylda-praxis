"""Thin reference application shared by CLI and HTTP transports."""

from __future__ import annotations

from typing import Any, Mapping

from .adapters.review_json import parse_review
from .domain.models import ApprovalEvidence, HypothesisArtifact, HypothesisRecord
from .domain.types import DecisionType, HypothesisState, MemoryClass, RejectionReason
from .ports.interfaces import ArtifactRepository
from .protocol.lifecycle import (
    add_benchmark,
    advance,
    decide,
    deflate,
    record_hostile_review,
    resume,
    run_preflight,
)


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _required_text(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required text")
    return value.strip()


class ReferenceApplication:
    def __init__(self, repository: ArtifactRepository) -> None:
        self.repository = repository

    def create(self, title: str) -> HypothesisRecord:
        record = HypothesisRecord.seed(title)
        self.repository.save(record, expected_revision=None)
        return record

    def list(self) -> tuple[HypothesisRecord, ...]:
        return self.repository.list()

    def get(self, artifact_id: str) -> HypothesisRecord:
        return self.repository.get(artifact_id)

    def advance(
        self,
        artifact_id: str,
        state: str,
        artifact_data: Mapping[str, Any] | None = None,
    ) -> HypothesisRecord:
        record = self.get(artifact_id)
        revision = record.revision
        target = HypothesisState(state)
        artifact = None
        if target is HypothesisState.WORKING:
            data = _object(artifact_data, "artifact")
            artifact = HypothesisArtifact().with_changes(**dict(data))
        updated = advance(record, target, artifact)
        self.repository.save(updated, expected_revision=revision)
        return updated

    def preflight(self, artifact_id: str):
        record = self.get(artifact_id)
        revision = record.revision
        peers = self.repository.list()
        negative_claims = tuple(
            memory.claim
            for peer in peers
            for memory in peer.memory_updates
            if memory.memory_class is MemoryClass.EPISTEMIC_NEGATIVE
        )
        updated, check = run_preflight(record, peers, negative_claims)
        self.repository.save(updated, expected_revision=revision)
        return check

    def benchmark(self, artifact_id: str, payload: Mapping[str, Any]):
        data = _object(payload, "benchmark")
        record = self.get(artifact_id)
        revision = record.revision
        updated, result = add_benchmark(
            record,
            baseline=data.get("baseline"),
            sources=data.get("sources"),
            existing_solution_search=data.get("existing_solution_search"),
            result=data.get("result"),
        )
        self.repository.save(updated, expected_revision=revision)
        return result

    def review(self, artifact_id: str, payload: Mapping[str, Any]):
        data = dict(_object(payload, "review"))
        benchmark_id = _required_text(data, "benchmark_id")
        data.pop("benchmark_id")
        draft = parse_review(data)
        record = self.get(artifact_id)
        revision = record.revision
        updated, result = record_hostile_review(record, benchmark_id, draft)
        self.repository.save(updated, expected_revision=revision)
        return result

    def deflate(self, artifact_id: str, payload: Mapping[str, Any]):
        data = _object(payload, "deflation")
        changes = _object(data.get("changes"), "changes")
        withdrawn = data.get("withdrawn_claims", [])
        if not isinstance(withdrawn, list):
            raise ValueError("withdrawn_claims must be a list")
        rationale = _required_text(data, "rationale")
        record = self.get(artifact_id)
        revision = record.revision
        peers = self.repository.list()
        negative_claims = tuple(
            memory.claim
            for peer in peers
            for memory in peer.memory_updates
            if memory.memory_class is MemoryClass.EPISTEMIC_NEGATIVE
        )
        updated, result = deflate(
            record,
            dict(changes),
            withdrawn,
            rationale,
            peers=peers,
            negative_claims=negative_claims,
        )
        self.repository.save(updated, expected_revision=revision)
        return result

    def decide(self, artifact_id: str, decision_name: str, payload: Mapping[str, Any]):
        data = _object(payload, "decision")
        if data.get("confirmed_by_human") is not True:
            raise ValueError("Decision requires confirmed_by_human=true")
        operator_id = _required_text(data, "operator_id")
        channel = str(data.get("channel") or "reference_interface").strip()
        rationale = _required_text(data, "rationale")
        decision_type = DecisionType(decision_name.upper())
        reason_raw = data.get("reason_code")
        reason = RejectionReason(str(reason_raw).upper()) if reason_raw else None
        record = self.get(artifact_id)
        revision = record.revision
        updated, memo = decide(
            record,
            decision_type,
            rationale,
            ApprovalEvidence(operator_id, channel),
            reason_code=reason,
            reentry_condition=data.get("reentry_condition"),
            review_date=data.get("review_date"),
            publication_target=data.get("publication_target"),
        )
        self.repository.save(updated, expected_revision=revision)
        return memo

    def resume(self, artifact_id: str, payload: Mapping[str, Any]) -> HypothesisRecord:
        data = _object(payload, "resume")
        parent = self.get(artifact_id)
        child = resume(
            parent,
            _required_text(data, "new_basis"),
            str(data.get("title") or "").strip() or None,
        )
        self.repository.save(child, expected_revision=None)
        return child
