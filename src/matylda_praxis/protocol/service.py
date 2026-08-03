"""Application service that coordinates ports around pure protocol functions."""

from __future__ import annotations

from ..domain.models import HypothesisRecord
from ..domain.types import DecisionType, RejectionReason
from ..ports.interfaces import (
    ArtifactRepository,
    BenchmarkProvider,
    BenchmarkRequest,
    DecisionRequest,
    HostileReviewer,
    HumanApproval,
    ReviewRequest,
)
from .errors import ApprovalDenied
from .lifecycle import add_benchmark, decide, record_hostile_review


class PraxisService:
    def __init__(
        self,
        repository: ArtifactRepository,
        benchmark_provider: BenchmarkProvider,
        reviewer: HostileReviewer,
        human_approval: HumanApproval,
    ) -> None:
        self._repository = repository
        self._benchmarker = benchmark_provider
        self._reviewer = reviewer
        self._approval = human_approval

    def capture(self, title: str) -> HypothesisRecord:
        record = HypothesisRecord.seed(title)
        self._repository.save(record, expected_revision=None)
        return record

    def benchmark(self, artifact_id: str):
        record = self._repository.get(artifact_id)
        revision = record.revision
        draft = self._benchmarker.benchmark(BenchmarkRequest(
            record.id, record.current.number, record.artifact,
        ))
        updated, result = add_benchmark(
            record,
            baseline=draft.baseline,
            sources=draft.sources,
            existing_solution_search=draft.existing_solution_search,
            result=draft.result,
        )
        self._repository.save(updated, expected_revision=revision)
        return result

    def review(self, artifact_id: str):
        record = self._repository.get(artifact_id)
        revision = record.revision
        benchmark = next(
            item for item in reversed(record.benchmark_results)
            if item.artifact_version == record.current.number
        )
        draft = self._reviewer.review(ReviewRequest(
            record.id, record.current.number, record.artifact, benchmark,
        ))
        updated, result = record_hostile_review(record, benchmark.benchmark_id, draft)
        self._repository.save(updated, expected_revision=revision)
        return result

    def decide(
        self,
        artifact_id: str,
        decision_type: DecisionType,
        rationale: str,
        *,
        reason_code: RejectionReason | None = None,
        reentry_condition: str | None = None,
        review_date: str | None = None,
        publication_target: str | None = None,
    ):
        record = self._repository.get(artifact_id)
        revision = record.revision
        request = DecisionRequest(record.id, record.current.number, decision_type, rationale)
        approval = self._approval.approve(request)
        if approval is None:
            raise ApprovalDenied("Human approval was denied or not supplied")
        updated, memo = decide(
            record,
            decision_type,
            rationale,
            approval,
            reason_code=reason_code,
            reentry_condition=reentry_condition,
            review_date=review_date,
            publication_target=publication_target,
        )
        self._repository.save(updated, expected_revision=revision)
        return memo
