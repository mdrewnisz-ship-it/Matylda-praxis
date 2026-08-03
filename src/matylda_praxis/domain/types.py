"""Closed vocabularies owned by the Praxis methodology."""

from __future__ import annotations

from enum import Enum


class HypothesisState(str, Enum):
    SEED = "seed"
    INCUBATOR = "incubator"
    EXPLORATION = "exploration"
    WORKING = "working"
    WAITING = "waiting"
    CEMETERY = "cemetery"


class DecisionType(str, Enum):
    TEST = "TEST"
    WAIT = "WAIT"
    REJECT = "REJECT"
    PUBLISH = "PUBLISH"


class ReviewRecommendation(str, Enum):
    REJECT = "REJECT"
    REVISE = "REVISE"
    TEST = "TEST"


class RejectionReason(str, Enum):
    FALSIFIED = "FALSIFIED"
    CONTRADICTED = "CONTRADICTED"
    REDUNDANT = "REDUNDANT"
    UNTESTABLE = "UNTESTABLE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    SUPERSEDED = "SUPERSEDED"


class MemoryClass(str, Enum):
    EPISTEMIC_NEGATIVE = "epistemic_negative"
    OPERATIONAL_RETIREMENT = "operational_retirement"


EPISTEMIC_NEGATIVE_REASONS = frozenset({
    RejectionReason.FALSIFIED,
    RejectionReason.CONTRADICTED,
})
