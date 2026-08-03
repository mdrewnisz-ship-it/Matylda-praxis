from __future__ import annotations

from dataclasses import replace

import pytest

from matylda_praxis.domain.models import (
    ApprovalEvidence,
    HostileReviewDraft,
    HypothesisArtifact,
    HypothesisRecord,
)
from matylda_praxis.domain.types import (
    DecisionType,
    HypothesisState,
    MemoryClass,
    RejectionReason,
    ReviewRecommendation,
)
from matylda_praxis.protocol.errors import ProtocolViolation
from matylda_praxis.protocol.lifecycle import (
    add_benchmark,
    advance,
    decide,
    deflate,
    record_hostile_review,
    resume,
    run_preflight,
)


def working_record(title: str = "Praxis hypothesis") -> HypothesisRecord:
    record = HypothesisRecord.seed(title)
    record = advance(record, HypothesisState.INCUBATOR)
    record = advance(record, HypothesisState.EXPLORATION)
    return advance(record, HypothesisState.WORKING, HypothesisArtifact(
        claim="A bounded pilot effect is measurable.",
        scope="One controlled pilot sample.",
        assumptions=("The measurement is stable.",),
        evidence_for=("Pilot observation.",),
        falsification_condition="No effect in the control sample.",
        next_test="Run one controlled comparison.",
        exploration_cost="30 min",
    ))


def reviewed_record(recommendation: ReviewRecommendation = ReviewRecommendation.TEST):
    record, check = run_preflight(working_record())
    assert check.passed
    record, benchmark = add_benchmark(
        record,
        baseline="The null model predicts no effect.",
        sources=("source:praxis",),
        existing_solution_search="Index and two synonyms checked.",
        result="No equivalent result found.",
    )
    record, review = record_hostile_review(record, benchmark.benchmark_id, HostileReviewDraft(
        strongest_objection="Selection bias may explain the effect.",
        counterexample="The effect disappears after randomization.",
        hidden_assumptions=("The sample is representative.",),
        existing_solution_search="One adjacent term remains unchecked.",
        falsification_test="Randomize assignment.",
        minimum_evidence_required="One controlled replication.",
        recommendation=recommendation,
        confidence=0.74,
    ))
    return record, benchmark, review


def test_complete_protocol_preserves_exact_evidence_chain():
    record, benchmark, review = reviewed_record()
    decided, memo = decide(
        record,
        DecisionType.TEST,
        "Run the bounded test.",
        ApprovalEvidence("operator-1", "test-console"),
    )

    assert memo.artifact_version == record.current.number
    assert memo.review_id == review.review_id
    assert review.benchmark_id == benchmark.benchmark_id
    assert benchmark.artifact_version == review.artifact_version
    assert decided.effective_state is HypothesisState.WORKING


def test_revise_requires_substantive_deflation_and_preserves_old_version():
    record, _, review = reviewed_record(ReviewRecommendation.REVISE)
    original = record.artifact

    with pytest.raises(ProtocolViolation, match="substantive deflation"):
        decide(
            record,
            DecisionType.TEST,
            "Proceed without revision.",
            ApprovalEvidence("operator-1", "test-console"),
        )
    with pytest.raises(ProtocolViolation, match="must change"):
        deflate(record, {}, (), "Ceremonial acknowledgement.")

    deflated, result = deflate(
        record,
        {"claim": "An effect may be measurable in this pilot sample."},
        ("The effect generalizes.",),
        "Narrowed after hostile review.",
    )
    waiting, memo = decide(
        deflated,
        DecisionType.WAIT,
        "Wait for independent replication.",
        ApprovalEvidence("operator-1", "test-console"),
        reentry_condition="Independent replication is available.",
        review_date="2026-10-01",
    )

    assert deflated.versions[-2].artifact == original
    assert result.review_id == review.review_id
    assert memo.artifact_version == deflated.current.number
    assert waiting.effective_state is HypothesisState.WAITING


def test_state_after_decision_is_derived_from_decision_memo():
    record, _, _ = reviewed_record()
    waiting, _ = decide(
        record,
        DecisionType.WAIT,
        "Wait for replication.",
        ApprovalEvidence("operator-1", "test-console"),
        reentry_condition="Replication available.",
        review_date="2026-10-01",
    )
    corrupted_cursor = replace(waiting, state=HypothesisState.CEMETERY)

    assert corrupted_cursor.effective_state is HypothesisState.WAITING


def test_linked_reentry_does_not_rewrite_parent_and_is_not_its_duplicate():
    record, _, _ = reviewed_record()
    waiting, _ = decide(
        record,
        DecisionType.WAIT,
        "Wait for replication.",
        ApprovalEvidence("operator-1", "test-console"),
        reentry_condition="Replication available.",
        review_date="2026-10-01",
    )
    child = resume(waiting, "Independent replication observed.")
    checked, preflight = run_preflight(child, peers=(waiting,))

    assert child.parent_id == waiting.id
    assert child.decision_memos == ()
    assert preflight.passed
    assert checked.current.artifact.evidence_for[-1] == "Independent replication observed."


def test_artifact_rejects_mass_assignment():
    artifact = HypothesisArtifact()
    with pytest.raises(ValueError, match="Unknown artifact fields"):
        artifact.with_changes(state="cemetery", decision_memos=[])


def test_broken_review_contract_fails_closed():
    record, _ = run_preflight(working_record())
    record, benchmark = add_benchmark(
        record,
        baseline="Null.",
        sources=("source",),
        existing_solution_search="Checked.",
        result="No match.",
    )
    broken = HostileReviewDraft(
        strongest_objection="",
        counterexample="Counterexample.",
        hidden_assumptions=(),
        existing_solution_search="Checked.",
        falsification_test="Test.",
        minimum_evidence_required="Evidence.",
        recommendation=ReviewRecommendation.REJECT,
        confidence=0.8,
    )

    with pytest.raises(ProtocolViolation, match="incomplete"):
        record_hostile_review(record, benchmark.benchmark_id, broken)


@pytest.mark.parametrize(
    ("reason", "expected_class"),
    [
        (RejectionReason.FALSIFIED, MemoryClass.EPISTEMIC_NEGATIVE),
        (RejectionReason.RESOURCE_LIMIT, MemoryClass.OPERATIONAL_RETIREMENT),
    ],
)
def test_rejection_distinguishes_negative_knowledge_from_retirement(reason, expected_class):
    record, _, _ = reviewed_record(ReviewRecommendation.REJECT)
    rejected, memo = decide(
        record,
        DecisionType.REJECT,
        "End this run for the stated reason.",
        ApprovalEvidence("operator-1", "test-console"),
        reason_code=reason,
    )

    assert rejected.memory_updates[-1].memory_class is expected_class
    assert rejected.memory_updates[-1].decision_id == memo.decision_id
