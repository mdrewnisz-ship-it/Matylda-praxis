"""Small, provider-neutral quality measurements for hostile reviews."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any, Iterable

from .domain.models import HostileReviewDraft


@dataclass(frozen=True, slots=True)
class EvaluationExpectation:
    recommendations: tuple[str, ...]
    objection_concepts: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    case_id: str
    contract_valid: bool
    recommendation: str | None
    recommendation_match: bool
    concept_hits: int
    concept_total: int
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    estimated_cost_usd: float
    raw_review: str
    error: str | None = None

    @property
    def concept_recall(self) -> float:
        return self.concept_hits / self.concept_total if self.concept_total else 1.0


def score_review(
    case_id: str,
    review: HostileReviewDraft,
    expectation: EvaluationExpectation,
    *,
    input_tokens: int,
    output_tokens: int,
    latency_seconds: float,
    estimated_cost_usd: float,
    raw_review: str,
) -> EvaluationResult:
    objection = review.strongest_objection.casefold()
    hits = sum(
        any(term.casefold() in objection for term in alternatives)
        for alternatives in expectation.objection_concepts
    )
    return EvaluationResult(
        case_id=case_id,
        contract_valid=True,
        recommendation=review.recommendation.value,
        recommendation_match=review.recommendation.value in expectation.recommendations,
        concept_hits=hits,
        concept_total=len(expectation.objection_concepts),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_seconds=latency_seconds,
        estimated_cost_usd=estimated_cost_usd,
        raw_review=raw_review,
    )


def failed_result(
    case_id: str,
    expectation: EvaluationExpectation,
    *,
    input_tokens: int,
    output_tokens: int,
    latency_seconds: float,
    estimated_cost_usd: float,
    raw_review: str,
    error: str,
) -> EvaluationResult:
    return EvaluationResult(
        case_id=case_id,
        contract_valid=False,
        recommendation=None,
        recommendation_match=False,
        concept_hits=0,
        concept_total=len(expectation.objection_concepts),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_seconds=latency_seconds,
        estimated_cost_usd=estimated_cost_usd,
        raw_review=raw_review,
        error=error,
    )


def estimate_token_cost(
    input_tokens: int,
    output_tokens: int,
    *,
    input_usd_per_million: float,
    output_usd_per_million: float,
) -> float:
    return (
        input_tokens * input_usd_per_million
        + output_tokens * output_usd_per_million
    ) / 1_000_000


def summarize(results: Iterable[EvaluationResult]) -> dict[str, Any]:
    values = tuple(results)
    valid = tuple(item for item in values if item.contract_valid)
    return {
        "cases": len(values),
        "contract_valid": len(valid),
        "contract_rate": len(valid) / len(values) if values else 0.0,
        "recommendation_matches": sum(item.recommendation_match for item in values),
        "recommendation_match_rate": (
            sum(item.recommendation_match for item in values) / len(values)
            if values else 0.0
        ),
        "mean_objection_concept_recall": (
            mean(item.concept_recall for item in values) if values else 0.0
        ),
        "input_tokens": sum(item.input_tokens for item in values),
        "output_tokens": sum(item.output_tokens for item in values),
        "total_estimated_cost_usd": sum(item.estimated_cost_usd for item in values),
        "mean_latency_seconds": (
            mean(item.latency_seconds for item in values) if values else 0.0
        ),
        "results": [asdict(item) | {"concept_recall": item.concept_recall} for item in values],
    }
