from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from threading import Barrier

import pytest

from matylda_praxis.adapters.approval import CallbackHumanApproval
from matylda_praxis.adapters.benchmark import CallableBenchmarkProvider
from matylda_praxis.adapters.memory import InMemoryArtifactRepository
from matylda_praxis.domain.models import HostileReviewDraft
from matylda_praxis.domain.types import DecisionType, HypothesisState, ReviewRecommendation
from matylda_praxis.protocol.errors import ApprovalDenied, ConcurrencyConflict, ProtocolViolation
from matylda_praxis.protocol.lifecycle import add_benchmark, advance, deflate, run_preflight
from matylda_praxis.protocol.service import PraxisService


def reviewer_draft(recommendation=ReviewRecommendation.TEST):
    return HostileReviewDraft(
        strongest_objection="Selection bias may explain the effect.",
        counterexample="The effect disappears after randomization.",
        hidden_assumptions=("The sample is representative.",),
        existing_solution_search="One adjacent term remains unchecked.",
        falsification_test="Randomize assignment.",
        minimum_evidence_required="One controlled replication.",
        recommendation=recommendation,
        confidence=0.74,
    )


def prepared_repository(artifact_factory):
    from matylda_praxis.domain.models import HypothesisRecord

    repository = InMemoryArtifactRepository()
    record = HypothesisRecord.seed("Adversarial E2E")
    record = advance(record, HypothesisState.INCUBATOR)
    record = advance(record, HypothesisState.EXPLORATION)
    record = advance(record, HypothesisState.WORKING, artifact_factory())
    record, check = run_preflight(record)
    assert check.passed
    repository.save(record, expected_revision=None)
    return repository, record.id


def benchmark_provider():
    return CallableBenchmarkProvider(lambda _: {
        "baseline": "The null model predicts no effect.",
        "sources": ["source:e2e"],
        "existing_solution_search": "Index and two synonyms checked.",
        "result": "No equivalent result found.",
    })


class FixedReviewer:
    def __init__(self, recommendation=ReviewRecommendation.TEST):
        self.recommendation = recommendation

    def review(self, request):
        return reviewer_draft(self.recommendation)


def test_full_revise_wait_run_is_auditable_and_provider_neutral(artifact_factory):
    repository, artifact_id = prepared_repository(artifact_factory)
    denied_service = PraxisService(
        repository,
        benchmark_provider(),
        FixedReviewer(ReviewRecommendation.REVISE),
        CallbackHumanApproval("operator-e2e", lambda _: False),
    )
    benchmark = denied_service.benchmark(artifact_id)
    review = denied_service.review(artifact_id)

    reviewed = repository.get(artifact_id)
    revision = reviewed.revision
    narrowed, deflation = deflate(
        reviewed,
        {"claim": "An effect may be measurable in this pilot sample."},
        ("The effect generalizes to every population.",),
        "Narrowed after the selection-bias objection.",
    )
    repository.save(narrowed, expected_revision=revision)

    before_denial = repository.get(artifact_id)
    with pytest.raises(ApprovalDenied):
        denied_service.decide(
            artifact_id,
            DecisionType.WAIT,
            "Wait for independent replication.",
            reentry_condition="Independent replication is available.",
            review_date="2026-10-01",
        )
    assert repository.get(artifact_id) == before_denial

    accepted_service = PraxisService(
        repository,
        benchmark_provider(),
        FixedReviewer(),
        CallbackHumanApproval("operator-e2e", lambda _: True, channel="e2e"),
    )
    decision = accepted_service.decide(
        artifact_id,
        DecisionType.WAIT,
        "Wait for independent replication.",
        reentry_condition="Independent replication is available.",
        review_date="2026-10-01",
    )
    final = repository.get(artifact_id)

    assert review.benchmark_id == benchmark.benchmark_id
    assert deflation.review_id == review.review_id
    assert decision.review_id == review.review_id
    assert decision.artifact_version == deflation.to_version
    assert final.effective_state is HypothesisState.WAITING
    assert len({event.event_id for event in final.events}) == len(final.events)
    serialized = json.dumps(asdict(final), sort_keys=True)
    assert "openai" not in serialized.casefold()
    assert "anthropic" not in serialized.casefold()


def test_two_concurrent_human_decisions_have_one_winner(
    artifact_factory,
):
    repository, artifact_id = prepared_repository(artifact_factory)
    setup = PraxisService(
        repository,
        benchmark_provider(),
        FixedReviewer(),
        CallbackHumanApproval("setup", lambda _: True),
    )
    setup.benchmark(artifact_id)
    setup.review(artifact_id)

    barrier = Barrier(2)

    def confirm(_):
        barrier.wait(timeout=2)
        return True

    service = PraxisService(
        repository,
        benchmark_provider(),
        FixedReviewer(),
        CallbackHumanApproval("concurrent-operator", confirm),
    )

    def attempt(label):
        try:
            return service.decide(artifact_id, DecisionType.TEST, label)
        except (ConcurrencyConflict, ProtocolViolation) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("operator-a", "operator-b")))

    successes = [item for item in results if not isinstance(item, Exception)]
    failures = [item for item in results if isinstance(item, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert len(repository.get(artifact_id).decision_memos) == 1


def test_reviewer_failure_never_creates_a_partial_review(artifact_factory):
    repository, artifact_id = prepared_repository(artifact_factory)

    class BrokenReviewer:
        def review(self, request):
            raise ProtocolViolation("provider returned malformed output")

    service = PraxisService(
        repository,
        benchmark_provider(),
        BrokenReviewer(),
        CallbackHumanApproval("operator", lambda _: True),
    )
    service.benchmark(artifact_id)
    before = repository.get(artifact_id)

    with pytest.raises(ProtocolViolation, match="malformed"):
        service.review(artifact_id)

    after = repository.get(artifact_id)
    assert after == before
    assert after.hostile_reviews == ()


def test_benchmark_change_during_review_prevents_stale_review_commit(artifact_factory):
    repository, artifact_id = prepared_repository(artifact_factory)
    setup = PraxisService(
        repository,
        benchmark_provider(),
        FixedReviewer(),
        CallbackHumanApproval("operator", lambda _: True),
    )
    setup.benchmark(artifact_id)

    class RacingReviewer:
        def review(self, request):
            current = repository.get(request.artifact_id)
            updated, _ = add_benchmark(
                current,
                baseline="New concurrent baseline.",
                sources=("source:concurrent",),
                existing_solution_search="Concurrent search.",
                result="Concurrent result.",
            )
            repository.save(updated, expected_revision=current.revision)
            return reviewer_draft()

    racing = PraxisService(
        repository,
        benchmark_provider(),
        RacingReviewer(),
        CallbackHumanApproval("operator", lambda _: True),
    )

    with pytest.raises(ConcurrencyConflict):
        racing.review(artifact_id)

    final = repository.get(artifact_id)
    assert len(final.benchmark_results) == 2
    assert final.hostile_reviews == ()


def test_adversarial_benchmark_payload_cannot_assign_protocol_state(artifact_factory):
    repository, artifact_id = prepared_repository(artifact_factory)
    malicious = CallableBenchmarkProvider(lambda _: {
        "baseline": "Null.",
        "sources": ["source"],
        "existing_solution_search": "Checked.",
        "result": "No match.",
        "state": "cemetery",
        "decision_memos": [{"decision": "PUBLISH"}],
    })
    service = PraxisService(
        repository,
        malicious,
        FixedReviewer(),
        CallbackHumanApproval("operator", lambda _: True),
    )

    with pytest.raises(ValueError, match="incomplete contract"):
        service.benchmark(artifact_id)
    record = repository.get(artifact_id)
    assert record.effective_state is HypothesisState.WORKING
    assert record.decision_memos == ()
