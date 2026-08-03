"""Pure lifecycle operations for one versioned hypothesis run."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any, Iterable

from ..domain.models import (
    ApprovalEvidence,
    ArtifactVersion,
    BenchmarkResult,
    DecisionMemo,
    DeflationRecord,
    HostileReview,
    HostileReviewDraft,
    HypothesisArtifact,
    HypothesisRecord,
    MemoryUpdate,
    PreflightCheck,
    ProtocolEvent,
    new_id,
    utc_now,
)
from ..domain.types import (
    DecisionType,
    EPISTEMIC_NEGATIVE_REASONS,
    HypothesisState,
    MemoryClass,
    RejectionReason,
    ReviewRecommendation,
)
from .errors import ProtocolViolation
from .preflight import artifact_issues, evaluate_preflight

EARLY_TRANSITIONS = {
    HypothesisState.SEED: HypothesisState.INCUBATOR,
    HypothesisState.INCUBATOR: HypothesisState.EXPLORATION,
    HypothesisState.EXPLORATION: HypothesisState.WORKING,
}


def _commit(record: HypothesisRecord, kind: str, payload: dict[str, Any], **changes: Any) -> HypothesisRecord:
    now = utc_now()
    event = ProtocolEvent(new_id("evt"), kind, record.id, payload, now)
    return replace(
        record,
        events=record.events + (event,),
        revision=record.revision + 1,
        updated_at=now,
        **changes,
    )


def _current_pass(record: HypothesisRecord) -> PreflightCheck | None:
    return next((
        check for check in reversed(record.preflight_checks)
        if check.artifact_version == record.current.number and check.passed
    ), None)


def advance(
    record: HypothesisRecord,
    target: HypothesisState,
    artifact: HypothesisArtifact | None = None,
) -> HypothesisRecord:
    if not isinstance(target, HypothesisState):
        raise ProtocolViolation("Transition target must be a HypothesisState")
    expected = EARLY_TRANSITIONS.get(record.effective_state)
    if expected is not target:
        raise ProtocolViolation(f"Cannot transition {record.effective_state.value} to {target.value}")
    changes: dict[str, Any] = {"state": target}
    payload: dict[str, Any] = {"from": record.effective_state.value, "to": target.value}
    if target is HypothesisState.WORKING:
        if artifact is None:
            raise ProtocolViolation("A working transition requires an artifact")
        issues = artifact_issues(artifact)
        if issues:
            raise ProtocolViolation("Working artifact is incomplete: " + ", ".join(i.field for i in issues))
        version = ArtifactVersion(record.current.number + 1, artifact, "working_artifact")
        changes["versions"] = record.versions + (version,)
        payload["artifact_version"] = version.number
    return _commit(record, "state_advanced", payload, **changes)


def run_preflight(
    record: HypothesisRecord,
    peers: Iterable[HypothesisRecord] = (),
    negative_claims: Iterable[str] = (),
) -> tuple[HypothesisRecord, PreflightCheck]:
    if record.effective_state is not HypothesisState.WORKING:
        raise ProtocolViolation("Preflight requires a working artifact")
    check = PreflightCheck(
        new_id("pre"),
        record.current.number,
        evaluate_preflight(record, peers, negative_claims),
    )
    updated = _commit(
        record,
        "preflight_completed",
        {"check_id": check.check_id, "passed": check.passed, "artifact_version": check.artifact_version},
        preflight_checks=record.preflight_checks + (check,),
    )
    return updated, check


def add_benchmark(
    record: HypothesisRecord,
    *,
    baseline: str,
    sources: Iterable[str],
    existing_solution_search: str,
    result: str,
) -> tuple[HypothesisRecord, BenchmarkResult]:
    if _current_pass(record) is None:
        raise ProtocolViolation("Benchmark requires a passing preflight for the current version")
    if (
        not isinstance(sources, (list, tuple))
        or any(not isinstance(item, str) for item in sources)
        or any(not isinstance(item, str) for item in (
            baseline, existing_solution_search, result,
        ))
    ):
        raise ProtocolViolation("Benchmark requires baseline, sources, solution search and result")
    clean_sources = tuple(item.strip() for item in sources if item.strip())
    values = (baseline.strip(), existing_solution_search.strip(), result.strip())
    if not all(values) or not clean_sources:
        raise ProtocolViolation("Benchmark requires baseline, sources, solution search and result")
    benchmark = BenchmarkResult(
        new_id("bench"),
        record.current.number,
        values[0],
        clean_sources,
        values[1],
        values[2],
    )
    updated = _commit(
        record,
        "benchmark_recorded",
        {"benchmark_id": benchmark.benchmark_id, "artifact_version": benchmark.artifact_version},
        benchmark_results=record.benchmark_results + (benchmark,),
    )
    return updated, benchmark


def _validate_review(draft: HostileReviewDraft) -> None:
    required = (
        draft.strongest_objection,
        draft.counterexample,
        draft.existing_solution_search,
        draft.falsification_test,
        draft.minimum_evidence_required,
    )
    if not all(isinstance(value, str) and value.strip() for value in required):
        raise ProtocolViolation("Hostile review contract is incomplete")
    if not isinstance(draft.hidden_assumptions, tuple) or any(
        not isinstance(item, str) for item in draft.hidden_assumptions
    ):
        raise ProtocolViolation("Hostile review contract is incomplete")
    if not isinstance(draft.recommendation, ReviewRecommendation):
        raise ProtocolViolation("Hostile review contract is incomplete")
    if (
        isinstance(draft.confidence, bool)
        or not isinstance(draft.confidence, (int, float))
        or not 0 <= draft.confidence <= 1
    ):
        raise ProtocolViolation("Review confidence must be between 0 and 1")


def record_hostile_review(
    record: HypothesisRecord,
    benchmark_id: str,
    draft: HostileReviewDraft,
) -> tuple[HypothesisRecord, HostileReview]:
    if not isinstance(draft, HostileReviewDraft):
        raise ProtocolViolation("Hostile review must use the fixed domain contract")
    _validate_review(draft)
    benchmark = next((item for item in record.benchmark_results if item.benchmark_id == benchmark_id), None)
    if benchmark is None or benchmark.artifact_version != record.current.number:
        raise ProtocolViolation("Review must reference the exact current-version benchmark")
    review = HostileReview(
        strongest_objection=draft.strongest_objection,
        counterexample=draft.counterexample,
        hidden_assumptions=draft.hidden_assumptions,
        existing_solution_search=draft.existing_solution_search,
        falsification_test=draft.falsification_test,
        minimum_evidence_required=draft.minimum_evidence_required,
        recommendation=draft.recommendation,
        confidence=draft.confidence,
        review_id=new_id("review"),
        artifact_version=record.current.number,
        benchmark_id=benchmark_id,
    )
    updated = _commit(
        record,
        "hostile_review_recorded",
        {"review_id": review.review_id, "benchmark_id": benchmark_id, "artifact_version": review.artifact_version},
        hostile_reviews=record.hostile_reviews + (review,),
    )
    return updated, review


def deflate(
    record: HypothesisRecord,
    changes: dict[str, Any],
    withdrawn_claims: Iterable[str],
    rationale: str,
    *,
    peers: Iterable[HypothesisRecord] = (),
    negative_claims: Iterable[str] = (),
) -> tuple[HypothesisRecord, DeflationRecord]:
    review = record.hostile_reviews[-1] if record.hostile_reviews else None
    if review is None or review.artifact_version != record.current.number:
        raise ProtocolViolation("Deflation requires the current hostile review")
    rationale = rationale.strip()
    if not rationale:
        raise ProtocolViolation("Deflation rationale is required")
    withdrawn = tuple(str(item).strip() for item in withdrawn_claims if str(item).strip())
    artifact = record.artifact.with_changes(**changes)
    changed_fields = tuple(
        field for field in record.artifact.__dataclass_fields__
        if getattr(record.artifact, field) != getattr(artifact, field)
    )
    if not changed_fields and not withdrawn:
        raise ProtocolViolation("Deflation must change the artifact or withdraw a claim")
    issues = artifact_issues(artifact)
    if issues:
        raise ProtocolViolation("Deflation produced an incomplete artifact: " + ", ".join(i.field for i in issues))
    version = ArtifactVersion(record.current.number + 1, artifact, "deflation")
    provisional = replace(record, versions=record.versions + (version,))
    post_issues = evaluate_preflight(provisional, peers, negative_claims)
    if post_issues:
        raise ProtocolViolation("Deflated artifact failed preflight: " + ", ".join(i.field for i in post_issues))
    check = PreflightCheck(new_id("pre"), version.number, ())
    result = DeflationRecord(
        new_id("defl"),
        review.review_id,
        record.current.number,
        version.number,
        changed_fields,
        withdrawn,
        rationale,
    )
    updated = _commit(
        record,
        "artifact_deflated",
        {"deflation_id": result.deflation_id, "review_id": review.review_id, "to_version": version.number},
        versions=record.versions + (version,),
        preflight_checks=record.preflight_checks + (check,),
        deflations=record.deflations + (result,),
    )
    return updated, result


def decide(
    record: HypothesisRecord,
    decision: DecisionType,
    rationale: str,
    approval: ApprovalEvidence,
    *,
    reason_code: RejectionReason | None = None,
    reentry_condition: str | None = None,
    review_date: str | None = None,
    publication_target: str | None = None,
) -> tuple[HypothesisRecord, DecisionMemo]:
    if not isinstance(decision, DecisionType):
        raise ProtocolViolation("Decision must use the bounded DecisionType vocabulary")
    if not isinstance(approval, ApprovalEvidence):
        raise ProtocolViolation("Decision requires explicit human approval evidence")
    if record.decision_memos:
        raise ProtocolViolation("This protocol run already has a DecisionMemo")
    if not approval.operator_id.strip() or not approval.channel.strip():
        raise ProtocolViolation("Decision requires explicit human approval evidence")
    rationale = rationale.strip()
    if not rationale:
        raise ProtocolViolation("Decision rationale is required")
    review = record.hostile_reviews[-1] if record.hostile_reviews else None
    deflation = next((
        item for item in reversed(record.deflations)
        if review is not None
        and item.review_id == review.review_id
        and item.to_version == record.current.number
    ), None)
    if review is None or (
        review.artifact_version != record.current.number and deflation is None
    ):
        raise ProtocolViolation("Decision requires a hostile review of the current version")
    benchmark = next((item for item in record.benchmark_results if item.benchmark_id == review.benchmark_id), None)
    if benchmark is None or benchmark.artifact_version != review.artifact_version:
        raise ProtocolViolation("Decision review is not bound to the benchmark it received")
    if _current_pass(record) is None:
        raise ProtocolViolation("Decision requires passing preflight for the current version")
    if review.recommendation is ReviewRecommendation.REVISE and not any(
        item.review_id == review.review_id for item in record.deflations
    ):
        raise ProtocolViolation("REVISE requires substantive deflation before decision")
    if decision is DecisionType.REJECT and reason_code is None:
        raise ProtocolViolation("REJECT requires a typed reason")
    if decision is DecisionType.WAIT:
        if not (reentry_condition or "").strip() or not (review_date or "").strip():
            raise ProtocolViolation("WAIT requires re-entry condition and review date")
        try:
            date.fromisoformat(str(review_date))
        except ValueError as exc:
            raise ProtocolViolation("review_date must use YYYY-MM-DD") from exc
    if decision is DecisionType.PUBLISH and not (publication_target or "").strip():
        raise ProtocolViolation("PUBLISH requires a publication target")
    memo = DecisionMemo(
        new_id("decision"),
        record.current.number,
        review.review_id,
        decision,
        rationale,
        approval,
        review.recommendation,
        reason_code,
        (reentry_condition or "").strip() or None,
        (review_date or "").strip() or None,
        (publication_target or "").strip() or None,
    )
    state = record.state
    if decision is DecisionType.WAIT:
        state = HypothesisState.WAITING
    elif decision is DecisionType.REJECT:
        state = HypothesisState.CEMETERY
    memory_updates = record.memory_updates
    if decision is DecisionType.REJECT and reason_code is not None:
        memory_class = (
            MemoryClass.EPISTEMIC_NEGATIVE
            if reason_code in EPISTEMIC_NEGATIVE_REASONS
            else MemoryClass.OPERATIONAL_RETIREMENT
        )
        memory_updates += (MemoryUpdate(
            new_id("memory"),
            memory_class,
            reason_code,
            record.artifact.claim,
            memo.decision_id,
        ),)
    updated = _commit(
        record,
        "decision_recorded",
        {"decision_id": memo.decision_id, "decision": decision.value, "review_id": review.review_id},
        state=state,
        decision_memos=record.decision_memos + (memo,),
        memory_updates=memory_updates,
    )
    return updated, memo


def resume(record: HypothesisRecord, new_basis: str, title: str | None = None) -> HypothesisRecord:
    if record.disposition not in {DecisionType.WAIT, DecisionType.REJECT}:
        raise ProtocolViolation("Only WAIT or REJECT can start a linked new run")
    new_basis = new_basis.strip()
    if not new_basis:
        raise ProtocolViolation("A linked new run requires a new evidential basis")
    artifact = record.artifact.with_changes(evidence_for=record.artifact.evidence_for + (new_basis,))
    now = utc_now()
    record_id = new_id("hyp")
    version = ArtifactVersion(1, artifact, "linked_reentry", now)
    event = ProtocolEvent(new_id("evt"), "linked_run_created", record_id, {"parent_id": record.id}, now)
    return HypothesisRecord(
        id=record_id,
        title=(title or f"{record.title} (new run)").strip(),
        state=HypothesisState.WORKING,
        versions=(version,),
        events=(event,),
        parent_id=record.id,
        created_at=now,
        updated_at=now,
    )
