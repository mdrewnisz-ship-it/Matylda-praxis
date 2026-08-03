"""Shared fail-closed JSON contract for model-backed reviewers."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Mapping

from ..domain.models import HostileReviewDraft
from ..domain.types import ReviewRecommendation
from ..ports.interfaces import ReviewRequest
from ..protocol.errors import ProtocolViolation

DARKROOM_SYSTEM = """You are an independent hostile reviewer.
Find the cheapest decisive reason why the artifact may be wrong, redundant,
untestable or needlessly complex. Review only the supplied artifact and
benchmark. Do not infer the author's intent. Be concise: keep each text field
under 100 words and list at most four hidden assumptions. Return only the
requested JSON.

Calibrate the recommendation as follows:
- REJECT only when the core claim is already falsified, redundant,
  self-sealing/untestable, or cannot be repaired without replacing it.
- REVISE when the strongest defect can be repaired by narrowing scope,
  withdrawing causal or novelty overclaim, or specifying a decisive test.
- TEST when the bounded claim and proposed next test already survive review.
"""

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "strongest_objection",
        "counterexample",
        "hidden_assumptions",
        "existing_solution_search",
        "falsification_test",
        "minimum_evidence_required",
        "recommendation",
        "confidence",
    ],
    "properties": {
        "strongest_objection": {"type": "string"},
        "counterexample": {"type": "string"},
        "hidden_assumptions": {"type": "array", "items": {"type": "string"}},
        "existing_solution_search": {"type": "string"},
        "falsification_test": {"type": "string"},
        "minimum_evidence_required": {"type": "string"},
        "recommendation": {"enum": ["REJECT", "REVISE", "TEST"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


def review_payload(request: ReviewRequest) -> str:
    # No generator rationale is part of ReviewRequest, so it cannot leak here.
    return json.dumps({
        "artifact_id": request.artifact_id,
        "artifact_version": request.artifact_version,
        "artifact": asdict(request.artifact),
        "benchmark": asdict(request.benchmark),
    }, ensure_ascii=True, sort_keys=True)


def parse_review(raw: str | Mapping[str, Any]) -> HostileReviewDraft:
    try:
        if isinstance(raw, str):
            data = json.loads(raw)
        elif isinstance(raw, Mapping):
            data = dict(raw)
        else:
            raise ValueError("review must be a JSON object")
        if not isinstance(data, dict):
            raise ValueError("review must be a JSON object")
        required = set(REVIEW_SCHEMA["required"])
        if set(data) != required:
            raise ValueError("review keys do not match the fixed contract")
        text_keys = required - {"hidden_assumptions", "recommendation", "confidence"}
        if any(not isinstance(data[key], str) for key in text_keys):
            raise ValueError("review text fields must be strings")
        values = {key: data[key].strip() for key in text_keys}
        if not all(values.values()):
            raise ValueError("review contains empty required text")
        raw_assumptions = data["hidden_assumptions"]
        if not isinstance(raw_assumptions, list) or any(
            not isinstance(item, str) for item in raw_assumptions
        ):
            raise ValueError("hidden_assumptions must be a list of strings")
        assumptions = tuple(
            item.strip() for item in raw_assumptions if item.strip()
        )
        raw_confidence = data["confidence"]
        if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, (int, float)):
            raise ValueError("confidence must be a number")
        confidence = float(raw_confidence)
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not isinstance(data["recommendation"], str):
            raise ValueError("recommendation must be a string")
        return HostileReviewDraft(
            **values,
            hidden_assumptions=assumptions,
            recommendation=ReviewRecommendation(str(data["recommendation"])),
            confidence=confidence,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProtocolViolation(f"Reviewer returned an invalid contract: {exc}") from exc
