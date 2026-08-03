"""Deterministic checks that run before model-based review."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..domain.models import HypothesisArtifact, HypothesisRecord, PreflightIssue
from ..domain.types import HypothesisState

EXPLORATION_COSTS = frozenset({
    "5 min",
    "30 min",
    "half day",
    "2 days",
    "experiment",
    "new capability",
})


def normalize_claim(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\W+", " ", value.casefold()).strip()


def artifact_issues(artifact: HypothesisArtifact) -> tuple[PreflightIssue, ...]:
    issues: list[PreflightIssue] = []
    required = {
        "claim": artifact.claim,
        "scope": artifact.scope,
        "falsification_condition": artifact.falsification_condition,
        "next_test": artifact.next_test,
        "exploration_cost": artifact.exploration_cost,
    }
    for field, value in required.items():
        if not isinstance(value, str):
            issues.append(PreflightIssue("invalid_type", field, f"{field} must be text"))
        elif not value.strip():
            issues.append(PreflightIssue("required", field, f"{field} is required"))
    for field in ("assumptions", "evidence_for", "evidence_against"):
        value = getattr(artifact, field)
        if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
            issues.append(PreflightIssue(
                "invalid_type", field, f"{field} must be a tuple of strings",
            ))
    if (
        isinstance(artifact.exploration_cost, str)
        and artifact.exploration_cost
        and artifact.exploration_cost not in EXPLORATION_COSTS
    ):
        issues.append(PreflightIssue(
            "invalid_cost",
            "exploration_cost",
            "exploration_cost is outside the bounded vocabulary",
        ))
    return tuple(issues)


def evaluate_preflight(
    record: HypothesisRecord,
    peers: Iterable[HypothesisRecord] = (),
    negative_claims: Iterable[str] = (),
) -> tuple[PreflightIssue, ...]:
    issues = list(artifact_issues(record.artifact))
    claim = normalize_claim(record.artifact.claim)
    if claim:
        for peer in peers:
            if peer.id == record.id or peer.id == record.parent_id:
                continue
            if peer.effective_state is HypothesisState.CEMETERY:
                continue
            if normalize_claim(peer.artifact.claim) == claim:
                issues.append(PreflightIssue(
                    "active_duplicate",
                    "claim",
                    f"claim duplicates active artifact {peer.id}",
                ))
                break
        if claim in {normalize_claim(item) for item in negative_claims if item.strip()}:
            issues.append(PreflightIssue(
                "negative_memory_match",
                "claim",
                "claim matches epistemic negative memory",
            ))
    return tuple(issues)
