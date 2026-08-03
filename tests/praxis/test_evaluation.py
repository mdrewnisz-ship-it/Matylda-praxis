from __future__ import annotations

import pytest

from matylda_praxis.domain.models import HostileReviewDraft
from matylda_praxis.domain.types import ReviewRecommendation
from matylda_praxis.evaluation import (
    EvaluationExpectation,
    estimate_token_cost,
    failed_result,
    score_review,
    summarize,
)


def draft(*, recommendation=ReviewRecommendation.REVISE):
    return HostileReviewDraft(
        strongest_objection="A concurrent release freeze confounds causal attribution.",
        counterexample="The incident rate falls without the checklist.",
        hidden_assumptions=("No simultaneous intervention.",),
        existing_solution_search="Interrupted time series exists.",
        falsification_test="Compare staggered adoption.",
        minimum_evidence_required="One controlled comparison.",
        recommendation=recommendation,
        confidence=0.8,
    )


def test_cost_uses_explicit_rates():
    assert estimate_token_cost(
        1_000_000, 500_000,
        input_usd_per_million=2,
        output_usd_per_million=10,
    ) == 7


def test_review_score_checks_recommendation_and_objection_concepts():
    result = score_review(
        "case-1",
        draft(),
        EvaluationExpectation(
            ("REVISE",),
            (("confound", "simultaneous"), ("causal", "attribute")),
        ),
        input_tokens=100,
        output_tokens=50,
        latency_seconds=1.2,
        estimated_cost_usd=0.001,
        raw_review="{}",
    )

    assert result.recommendation_match
    assert result.concept_recall == 1


def test_summary_keeps_contract_failure_in_denominators():
    expectation = EvaluationExpectation(("TEST",), (("sample",),))
    success = score_review(
        "ok", draft(recommendation=ReviewRecommendation.TEST), expectation,
        input_tokens=100, output_tokens=50, latency_seconds=1,
        estimated_cost_usd=0.001, raw_review="{}",
    )
    failure = failed_result(
        "bad", expectation,
        input_tokens=80, output_tokens=20, latency_seconds=2,
        estimated_cost_usd=0.0005, raw_review="not-json", error="invalid",
    )

    summary = summarize((success, failure))

    assert summary["contract_rate"] == 0.5
    assert summary["recommendation_match_rate"] == 0.5
    assert summary["total_estimated_cost_usd"] == pytest.approx(0.0015)
