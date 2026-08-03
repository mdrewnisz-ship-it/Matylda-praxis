"""Ports keep methodology independent from vendors and infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.models import (
    ApprovalEvidence,
    BenchmarkResult,
    HostileReviewDraft,
    HypothesisArtifact,
    HypothesisRecord,
)
from ..domain.types import DecisionType


@dataclass(frozen=True, slots=True)
class BenchmarkRequest:
    artifact_id: str
    artifact_version: int
    artifact: HypothesisArtifact


@dataclass(frozen=True, slots=True)
class BenchmarkDraft:
    baseline: str
    sources: tuple[str, ...]
    existing_solution_search: str
    result: str


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    artifact_id: str
    artifact_version: int
    artifact: HypothesisArtifact
    benchmark: BenchmarkResult


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    artifact_id: str
    artifact_version: int
    decision: DecisionType
    rationale: str


class ArtifactRepository(Protocol):
    def get(self, artifact_id: str) -> HypothesisRecord: ...

    def list(self) -> tuple[HypothesisRecord, ...]: ...

    def save(
        self,
        record: HypothesisRecord,
        *,
        expected_revision: int | None,
    ) -> None: ...


class BenchmarkProvider(Protocol):
    def benchmark(self, request: BenchmarkRequest) -> BenchmarkDraft: ...


class HostileReviewer(Protocol):
    def review(self, request: ReviewRequest) -> HostileReviewDraft: ...


class HumanApproval(Protocol):
    def approve(self, request: DecisionRequest) -> ApprovalEvidence | None: ...
