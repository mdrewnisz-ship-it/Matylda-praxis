from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from matylda_praxis.adapters.anthropic import AnthropicHostileReviewer
from matylda_praxis.adapters.approval import CallbackHumanApproval
from matylda_praxis.adapters.benchmark import CallableBenchmarkProvider
from matylda_praxis.adapters.memory import InMemoryArtifactRepository
from matylda_praxis.adapters.openai import OpenAIHostileReviewer
from matylda_praxis.domain.models import (
    BenchmarkResult,
    HostileReviewDraft,
    HypothesisArtifact,
    HypothesisRecord,
)
from matylda_praxis.domain.types import DecisionType, HypothesisState, ReviewRecommendation
from matylda_praxis.ports.interfaces import DecisionRequest, ReviewRequest
from matylda_praxis.protocol.errors import ConcurrencyConflict, ProtocolViolation
from matylda_praxis.protocol.lifecycle import advance, run_preflight
from matylda_praxis.protocol.service import PraxisService


VALID_REVIEW = {
    "strongest_objection": "Selection bias.",
    "counterexample": "Randomized sample has no effect.",
    "hidden_assumptions": ["Representative sample."],
    "existing_solution_search": "Adjacent term checked.",
    "falsification_test": "Randomize assignment.",
    "minimum_evidence_required": "One replication.",
    "recommendation": "REVISE",
    "confidence": 0.72,
}


def review_request() -> ReviewRequest:
    artifact = HypothesisArtifact(
        claim="A pilot effect exists.",
        scope="Pilot.",
        falsification_condition="No control effect.",
        next_test="Controlled test.",
        exploration_cost="30 min",
    )
    benchmark = BenchmarkResult(
        "bench-1", 2, "Null.", ("source",), "Checked.", "No match.",
    )
    return ReviewRequest("hyp-1", 2, artifact, benchmark)


def test_openai_adapter_sends_only_artifact_and_benchmark():
    captured = {}

    class Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=json.dumps(VALID_REVIEW))

    reviewer = OpenAIHostileReviewer(SimpleNamespace(responses=Responses()), "test-model")
    result = reviewer.review(review_request())

    assert result.recommendation is ReviewRecommendation.REVISE
    assert "rationale" not in captured["input"]
    assert captured["max_output_tokens"] == 1600
    assert set(json.loads(captured["input"])) == {
        "artifact_id", "artifact_version", "artifact", "benchmark",
    }


def test_anthropic_adapter_uses_the_same_fail_closed_contract():
    captured = {}

    class Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(
                type="text", text=json.dumps(VALID_REVIEW),
            )])

    reviewer = AnthropicHostileReviewer(SimpleNamespace(messages=Messages()), "test-model")
    assert reviewer.review(review_request()).confidence == 0.72
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert captured["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert "minimum" not in captured["output_config"]["format"]["schema"]["properties"]["confidence"]


def test_provider_adapters_forward_explicit_reasoning_effort():
    openai_captured = {}
    anthropic_captured = {}

    class Responses:
        def create(self, **kwargs):
            openai_captured.update(kwargs)
            return SimpleNamespace(output_text=json.dumps(VALID_REVIEW))

    class Messages:
        def create(self, **kwargs):
            anthropic_captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(
                type="text", text=json.dumps(VALID_REVIEW),
            )])

    OpenAIHostileReviewer(
        SimpleNamespace(responses=Responses()), "test-model",
        reasoning_effort="low",
    ).review(review_request())
    AnthropicHostileReviewer(
        SimpleNamespace(messages=Messages()), "test-model", effort="low",
    ).review(review_request())

    assert openai_captured["reasoning"] == {"effort": "low"}
    assert anthropic_captured["output_config"]["effort"] == "low"

    class BrokenMessages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="not-json")])

    broken = AnthropicHostileReviewer(SimpleNamespace(messages=BrokenMessages()), "test-model")
    with pytest.raises(ProtocolViolation, match="invalid contract"):
        broken.review(review_request())


def test_repository_rejects_stale_writes():
    repository = InMemoryArtifactRepository()
    record = HypothesisRecord.seed("Concurrency")
    repository.save(record, expected_revision=None)

    with pytest.raises(ConcurrencyConflict):
        repository.save(record, expected_revision=3)


def test_human_approval_is_explicit_and_attributed():
    request = DecisionRequest("hyp-1", 2, DecisionType.TEST, "Run test.")
    denied = CallbackHumanApproval("operator-1", lambda _: False)
    accepted = CallbackHumanApproval("operator-1", lambda _: True, channel="desktop")

    assert denied.approve(request) is None
    evidence = accepted.approve(request)
    assert evidence is not None
    assert evidence.operator_id == "operator-1"
    assert evidence.channel == "desktop"


def test_service_orchestrates_replaceable_ports_without_provider_state_in_domain():
    repository = InMemoryArtifactRepository()
    record = HypothesisRecord.seed("Port orchestration")
    record = advance(record, HypothesisState.INCUBATOR)
    record = advance(record, HypothesisState.EXPLORATION)
    record = advance(record, HypothesisState.WORKING, review_request().artifact)
    record, _ = run_preflight(record)
    repository.save(record, expected_revision=None)

    benchmarker = CallableBenchmarkProvider(lambda _: {
        "baseline": "Null.",
        "sources": ["source"],
        "existing_solution_search": "Checked.",
        "result": "No match.",
    })

    class Reviewer:
        def review(self, request):
            return HostileReviewDraft(
                strongest_objection="Selection bias.",
                counterexample="Randomized sample has no effect.",
                hidden_assumptions=("Representative sample.",),
                existing_solution_search="Adjacent term checked.",
                falsification_test="Randomize assignment.",
                minimum_evidence_required="One replication.",
                recommendation=ReviewRecommendation.TEST,
                confidence=0.72,
            )

    service = PraxisService(
        repository,
        benchmarker,
        Reviewer(),
        CallbackHumanApproval("operator-1", lambda _: True),
    )

    benchmark = service.benchmark(record.id)
    review = service.review(record.id)
    decision = service.decide(record.id, DecisionType.TEST, "Run the bounded test.")

    assert review.benchmark_id == benchmark.benchmark_id
    assert decision.review_id == review.review_id
    assert repository.get(record.id).disposition is DecisionType.TEST
