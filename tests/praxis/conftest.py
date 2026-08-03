from __future__ import annotations

import pytest

from matylda_praxis.domain.models import (
    BenchmarkResult,
    HostileReviewDraft,
    HypothesisArtifact,
    HypothesisRecord,
)
from matylda_praxis.domain.types import HypothesisState, ReviewRecommendation
from matylda_praxis.ports.interfaces import ReviewRequest
from matylda_praxis.protocol.lifecycle import (
    add_benchmark,
    advance,
    record_hostile_review,
    run_preflight,
)


@pytest.fixture()
def artifact_factory():
    def build(claim: str = "A bounded pilot effect is measurable.") -> HypothesisArtifact:
        return HypothesisArtifact(
            claim=claim,
            scope="One controlled pilot sample.",
            assumptions=("The measurement is stable.",),
            evidence_for=("Pilot observation.",),
            evidence_against=(),
            falsification_condition="No effect in the control sample.",
            next_test="Run one controlled comparison.",
            exploration_cost="30 min",
        )

    return build


@pytest.fixture()
def review_request(artifact_factory):
    artifact = artifact_factory()
    benchmark = BenchmarkResult(
        "bench-contract",
        2,
        "The null model predicts no effect.",
        ("source:contract",),
        "Index and two synonyms checked.",
        "No equivalent result found.",
    )
    return ReviewRequest("hyp-contract", 2, artifact, benchmark)


@pytest.fixture()
def review_factory():
    def build(
        recommendation: ReviewRecommendation = ReviewRecommendation.TEST,
    ) -> HostileReviewDraft:
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

    return build


@pytest.fixture()
def working_factory(artifact_factory):
    def build(
        title: str = "Praxis contract hypothesis",
        claim: str = "A bounded pilot effect is measurable.",
    ) -> HypothesisRecord:
        record = HypothesisRecord.seed(title)
        record = advance(record, HypothesisState.INCUBATOR)
        record = advance(record, HypothesisState.EXPLORATION)
        return advance(record, HypothesisState.WORKING, artifact_factory(claim))

    return build


@pytest.fixture()
def reviewed_factory(working_factory, review_factory):
    def build(
        recommendation: ReviewRecommendation = ReviewRecommendation.TEST,
        title: str = "Praxis reviewed hypothesis",
    ):
        record, check = run_preflight(working_factory(title))
        assert check.passed
        record, benchmark = add_benchmark(
            record,
            baseline="The null model predicts no effect.",
            sources=("source:contract",),
            existing_solution_search="Index and two synonyms checked.",
            result="No equivalent result found.",
        )
        record, review = record_hostile_review(
            record,
            benchmark.benchmark_id,
            review_factory(recommendation),
        )
        return record, benchmark, review

    return build
