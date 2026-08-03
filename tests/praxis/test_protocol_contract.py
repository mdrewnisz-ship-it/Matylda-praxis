from __future__ import annotations

from dataclasses import replace

import pytest

from matylda_praxis.domain.models import (
    ApprovalEvidence,
    ArtifactVersion,
    HypothesisArtifact,
)
from matylda_praxis.domain.types import (
    DecisionType,
    HypothesisState,
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


def approval() -> ApprovalEvidence:
    return ApprovalEvidence("contract-operator", "contract-suite")


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (HypothesisState.SEED, HypothesisState.EXPLORATION),
        (HypothesisState.SEED, HypothesisState.WORKING),
        (HypothesisState.INCUBATOR, HypothesisState.WORKING),
    ],
)
def test_lifecycle_cannot_skip_required_stages(source, target, artifact_factory):
    from matylda_praxis.domain.models import HypothesisRecord

    record = HypothesisRecord.seed("No stage skipping")
    if source is HypothesisState.INCUBATOR:
        record = advance(record, HypothesisState.INCUBATOR)

    with pytest.raises(ProtocolViolation, match="Cannot transition"):
        advance(record, target, artifact_factory() if target is HypothesisState.WORKING else None)


def test_runtime_enum_and_record_types_fail_as_protocol_violations(working_factory, review_factory):
    from matylda_praxis.domain.models import HypothesisRecord

    seed = HypothesisRecord.seed("Runtime enum attack")
    with pytest.raises(ProtocolViolation):
        advance(seed, "incubator")  # type: ignore[arg-type]

    working, _ = run_preflight(working_factory())
    working, benchmark = add_benchmark(
        working,
        baseline="Null.",
        sources=("source",),
        existing_solution_search="Checked.",
        result="No match.",
    )
    with pytest.raises(ProtocolViolation):
        record_hostile_review(
            working,
            benchmark.benchmark_id,
            {"recommendation": "TEST"},  # type: ignore[arg-type]
        )


def test_working_artifact_cannot_omit_falsification(working_factory):
    from matylda_praxis.domain.models import HypothesisRecord

    record = HypothesisRecord.seed("Incomplete artifact")
    record = advance(record, HypothesisState.INCUBATOR)
    record = advance(record, HypothesisState.EXPLORATION)

    with pytest.raises(ProtocolViolation, match="falsification_condition"):
        advance(record, HypothesisState.WORKING, HypothesisArtifact(
            claim="An attractive story.",
            scope="Pilot.",
            next_test="Observe more.",
            exploration_cost="30 min",
        ))


@pytest.mark.parametrize(
    "artifact",
    [
        HypothesisArtifact(
            claim=7,  # type: ignore[arg-type]
            scope="Pilot.",
            falsification_condition="No effect.",
            next_test="Test.",
            exploration_cost="30 min",
        ),
        HypothesisArtifact(
            claim="Claim.",
            scope="Pilot.",
            assumptions="not-a-list",  # type: ignore[arg-type]
            falsification_condition="No effect.",
            next_test="Test.",
            exploration_cost="30 min",
        ),
    ],
)
def test_runtime_types_cannot_bypass_artifact_contract(artifact):
    from matylda_praxis.domain.models import HypothesisRecord

    record = HypothesisRecord.seed("Runtime type attack")
    record = advance(record, HypothesisState.INCUBATOR)
    record = advance(record, HypothesisState.EXPLORATION)
    with pytest.raises(ProtocolViolation, match="incomplete"):
        advance(record, HypothesisState.WORKING, artifact)

    with pytest.raises(ValueError):
        HypothesisArtifact().with_changes(assumptions=[{"not": "text"}])


def test_preflight_detects_active_duplicate_but_not_linked_parent(working_factory):
    parent = working_factory("Parent", "The same normalized CLAIM exists!")
    duplicate = working_factory("Duplicate", "the same normalized claim exists")
    _, duplicate_check = run_preflight(duplicate, peers=(parent,))
    linked = replace(duplicate, parent_id=parent.id)
    _, linked_check = run_preflight(linked, peers=(parent,))

    assert [issue.code for issue in duplicate_check.issues] == ["active_duplicate"]
    assert linked_check.passed


def test_preflight_surfaces_negative_memory(working_factory):
    record = working_factory(claim="A previously falsified mechanism works.")
    _, check = run_preflight(
        record,
        negative_claims=("a previously falsified mechanism works",),
    )

    assert [issue.code for issue in check.issues] == ["negative_memory_match"]


def test_old_preflight_cannot_authorize_a_new_unchecked_version(working_factory):
    record, check = run_preflight(working_factory())
    assert check.passed
    unchecked = replace(
        record,
        versions=record.versions + (ArtifactVersion(
            record.current.number + 1,
            record.artifact.with_changes(claim="A materially different claim."),
            "external_edit",
        ),),
    )

    with pytest.raises(ProtocolViolation, match="passing preflight"):
        add_benchmark(
            unchecked,
            baseline="Null.",
            sources=("source",),
            existing_solution_search="Checked.",
            result="No match.",
        )


@pytest.mark.parametrize(
    "missing",
    ["baseline", "sources", "existing_solution_search", "result"],
)
def test_benchmark_contract_is_complete(working_factory, missing):
    record, _ = run_preflight(working_factory())
    values = {
        "baseline": "Null.",
        "sources": ("source",),
        "existing_solution_search": "Checked.",
        "result": "No match.",
    }
    values[missing] = () if missing == "sources" else ""

    with pytest.raises(ProtocolViolation, match="Benchmark requires"):
        add_benchmark(record, **values)


def test_domain_benchmark_rejects_non_string_sources(working_factory):
    record, _ = run_preflight(working_factory())
    with pytest.raises(ProtocolViolation, match="Benchmark requires"):
        add_benchmark(
            record,
            baseline="Null.",
            sources="source",  # type: ignore[arg-type]
            existing_solution_search="Checked.",
            result="No match.",
        )


def test_review_cannot_attach_to_unknown_or_stale_benchmark(
    working_factory,
    review_factory,
):
    record, _ = run_preflight(working_factory())
    record, benchmark = add_benchmark(
        record,
        baseline="Null.",
        sources=("source",),
        existing_solution_search="Checked.",
        result="No match.",
    )

    with pytest.raises(ProtocolViolation, match="exact current-version benchmark"):
        record_hostile_review(record, "bench_unknown", review_factory())

    changed = replace(
        record,
        versions=record.versions + (ArtifactVersion(
            record.current.number + 1,
            record.artifact.with_changes(claim="Changed claim."),
            "external_edit",
        ),),
    )
    with pytest.raises(ProtocolViolation, match="exact current-version benchmark"):
        record_hostile_review(changed, benchmark.benchmark_id, review_factory())


def test_review_keeps_the_exact_benchmark_when_multiple_exist(
    working_factory,
    review_factory,
):
    record, _ = run_preflight(working_factory())
    record, first = add_benchmark(
        record,
        baseline="Baseline A.",
        sources=("source-a",),
        existing_solution_search="Search A.",
        result="Result A.",
    )
    record, _ = add_benchmark(
        record,
        baseline="Baseline B.",
        sources=("source-b",),
        existing_solution_search="Search B.",
        result="Result B.",
    )
    _, review = record_hostile_review(record, first.benchmark_id, review_factory())

    assert review.benchmark_id == first.benchmark_id


def test_decision_requires_review_and_current_preflight(working_factory):
    record, _ = run_preflight(working_factory())
    with pytest.raises(ProtocolViolation, match="hostile review"):
        decide(record, DecisionType.TEST, "Proceed.", approval())


def test_decision_rejects_forged_runtime_approval_type(reviewed_factory):
    record, _, _ = reviewed_factory()
    with pytest.raises(ProtocolViolation, match="approval"):
        decide(
            record,
            DecisionType.TEST,
            "Proceed.",
            {"operator_id": "model"},  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("decision_type", "kwargs", "message"),
    [
        (DecisionType.WAIT, {}, "re-entry condition"),
        (
            DecisionType.WAIT,
            {"reentry_condition": "New data.", "review_date": "01-10-2026"},
            "YYYY-MM-DD",
        ),
        (DecisionType.REJECT, {}, "typed reason"),
        (DecisionType.PUBLISH, {}, "publication target"),
    ],
)
def test_each_decision_has_its_specific_contract(reviewed_factory, decision_type, kwargs, message):
    record, _, _ = reviewed_factory()
    with pytest.raises(ProtocolViolation, match=message):
        decide(record, decision_type, "Decision rationale.", approval(), **kwargs)


def test_one_run_can_have_only_one_decision(reviewed_factory):
    record, _, _ = reviewed_factory()
    decided, _ = decide(record, DecisionType.TEST, "Run test.", approval())

    with pytest.raises(ProtocolViolation, match="already has"):
        decide(decided, DecisionType.TEST, "Run again.", approval())


def test_deflation_cannot_erase_a_required_field(reviewed_factory):
    record, _, _ = reviewed_factory(ReviewRecommendation.REVISE)
    with pytest.raises(ProtocolViolation, match="falsification_condition"):
        deflate(
            record,
            {"falsification_condition": ""},
            (),
            "Make the claim impossible to test.",
        )


def test_resume_requires_terminal_decision_and_new_basis(reviewed_factory):
    record, _, _ = reviewed_factory()
    with pytest.raises(ProtocolViolation, match="Only WAIT or REJECT"):
        resume(record, "New evidence.")

    waiting, _ = decide(
        record,
        DecisionType.WAIT,
        "Wait.",
        approval(),
        reentry_condition="New data.",
        review_date="2026-10-01",
    )
    with pytest.raises(ProtocolViolation, match="new evidential basis"):
        resume(waiting, "")
