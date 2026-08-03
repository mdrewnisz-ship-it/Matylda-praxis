"""Immutable records passed through the Praxis protocol."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .types import (
    DecisionType,
    HypothesisState,
    MemoryClass,
    RejectionReason,
    ReviewRecommendation,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass(frozen=True, slots=True)
class HypothesisArtifact:
    claim: str = ""
    scope: str = ""
    assumptions: tuple[str, ...] = ()
    evidence_for: tuple[str, ...] = ()
    evidence_against: tuple[str, ...] = ()
    falsification_condition: str = ""
    next_test: str = ""
    exploration_cost: str = ""

    def with_changes(self, **changes: Any) -> "HypothesisArtifact":
        allowed = set(self.__dataclass_fields__)
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unknown artifact fields: {', '.join(sorted(unknown))}")
        normalized = dict(changes)
        for name in ("assumptions", "evidence_for", "evidence_against"):
            if name in normalized:
                if (
                    not isinstance(normalized[name], (list, tuple))
                    or any(not isinstance(item, str) for item in normalized[name])
                ):
                    raise ValueError(f"{name} must be a list or tuple")
                normalized[name] = tuple(item.strip() for item in normalized[name] if item.strip())
        for name in allowed - {"assumptions", "evidence_for", "evidence_against"}:
            if name in normalized:
                if not isinstance(normalized[name], str):
                    raise ValueError(f"{name} must be text")
                normalized[name] = normalized[name].strip()
        return replace(self, **normalized)


@dataclass(frozen=True, slots=True)
class ArtifactVersion:
    number: int
    artifact: HypothesisArtifact
    reason: str
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class PreflightIssue:
    code: str
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    check_id: str
    artifact_version: int
    issues: tuple[PreflightIssue, ...]
    checked_at: str = field(default_factory=utc_now)

    @property
    def passed(self) -> bool:
        return not self.issues


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    benchmark_id: str
    artifact_version: int
    baseline: str
    sources: tuple[str, ...]
    existing_solution_search: str
    result: str
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class HostileReviewDraft:
    strongest_objection: str
    counterexample: str
    hidden_assumptions: tuple[str, ...]
    existing_solution_search: str
    falsification_test: str
    minimum_evidence_required: str
    recommendation: ReviewRecommendation
    confidence: float


@dataclass(frozen=True, slots=True)
class HostileReview(HostileReviewDraft):
    review_id: str
    artifact_version: int
    benchmark_id: str
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class DeflationRecord:
    deflation_id: str
    review_id: str
    from_version: int
    to_version: int
    changed_fields: tuple[str, ...]
    withdrawn_claims: tuple[str, ...]
    rationale: str
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ApprovalEvidence:
    operator_id: str
    channel: str
    confirmed_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class DecisionMemo:
    decision_id: str
    artifact_version: int
    review_id: str
    decision: DecisionType
    rationale: str
    approval: ApprovalEvidence
    recommendation_seen: ReviewRecommendation
    reason_code: RejectionReason | None = None
    reentry_condition: str | None = None
    review_date: str | None = None
    publication_target: str | None = None
    decided_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class MemoryUpdate:
    memory_id: str
    memory_class: MemoryClass
    reason_code: RejectionReason
    claim: str
    decision_id: str
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ProtocolEvent:
    event_id: str
    kind: str
    artifact_id: str
    payload: Mapping[str, Any]
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class HypothesisRecord:
    id: str
    title: str
    state: HypothesisState
    versions: tuple[ArtifactVersion, ...]
    preflight_checks: tuple[PreflightCheck, ...] = ()
    benchmark_results: tuple[BenchmarkResult, ...] = ()
    hostile_reviews: tuple[HostileReview, ...] = ()
    deflations: tuple[DeflationRecord, ...] = ()
    decision_memos: tuple[DecisionMemo, ...] = ()
    memory_updates: tuple[MemoryUpdate, ...] = ()
    events: tuple[ProtocolEvent, ...] = ()
    parent_id: str | None = None
    revision: int = 0
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def seed(cls, title: str) -> "HypothesisRecord":
        title = title.strip()
        if not title:
            raise ValueError("Hypothesis title is required")
        now = utc_now()
        record_id = new_id("hyp")
        version = ArtifactVersion(1, HypothesisArtifact(), "created", now)
        event = ProtocolEvent(new_id("evt"), "hypothesis_created", record_id, {}, now)
        return cls(
            id=record_id,
            title=title,
            state=HypothesisState.SEED,
            versions=(version,),
            events=(event,),
            created_at=now,
            updated_at=now,
        )

    @property
    def current(self) -> ArtifactVersion:
        return self.versions[-1]

    @property
    def artifact(self) -> HypothesisArtifact:
        return self.current.artifact

    @property
    def disposition(self) -> DecisionType | None:
        return self.decision_memos[-1].decision if self.decision_memos else None

    @property
    def effective_state(self) -> HypothesisState:
        if not self.decision_memos:
            return self.state
        decision = self.decision_memos[-1].decision
        if decision is DecisionType.WAIT:
            return HypothesisState.WAITING
        if decision is DecisionType.REJECT:
            return HypothesisState.CEMETERY
        return HypothesisState.WORKING
