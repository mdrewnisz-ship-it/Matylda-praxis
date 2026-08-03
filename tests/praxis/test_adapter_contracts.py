from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest

from matylda_praxis.adapters.anthropic import AnthropicHostileReviewer
from matylda_praxis.adapters.benchmark import CallableBenchmarkProvider
from matylda_praxis.adapters.memory import InMemoryArtifactRepository
from matylda_praxis.adapters.openai import OpenAIHostileReviewer
from matylda_praxis.adapters.review_json import parse_review
from matylda_praxis.domain.models import HypothesisRecord
from matylda_praxis.ports.interfaces import BenchmarkRequest
from matylda_praxis.protocol.errors import ConcurrencyConflict, ProtocolViolation


def valid_review() -> dict:
    return {
        "strongest_objection": "Selection bias.",
        "counterexample": "Randomized sample has no effect.",
        "hidden_assumptions": ["Representative sample."],
        "existing_solution_search": "Adjacent term checked.",
        "falsification_test": "Randomize assignment.",
        "minimum_evidence_required": "One replication.",
        "recommendation": "TEST",
        "confidence": 0.72,
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.pop("counterexample"),
        lambda data: data.update({"unexpected_decree": "accept"}),
        lambda data: data.update({"confidence": 1.2}),
        lambda data: data.update({"confidence": True}),
        lambda data: data.update({"hidden_assumptions": "not-a-list"}),
        lambda data: data.update({"hidden_assumptions": [{"claim": "not text"}]}),
        lambda data: data.update({"recommendation": "PUBLISH"}),
    ],
)
def test_review_parser_fails_closed_for_every_contract_violation(mutate):
    data = valid_review()
    mutate(data)
    with pytest.raises(ProtocolViolation, match="invalid contract"):
        parse_review(data)


def test_provider_adapters_produce_the_same_domain_contract(review_request):
    payload = json.dumps(valid_review())

    class Responses:
        def create(self, **kwargs):
            return SimpleNamespace(output_text=payload)

    class Messages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=payload)])

    openai_result = OpenAIHostileReviewer(
        SimpleNamespace(responses=Responses()), "openai-test",
    ).review(review_request)
    anthropic_result = AnthropicHostileReviewer(
        SimpleNamespace(messages=Messages()), "anthropic-test",
    ).review(review_request)

    assert openai_result == anthropic_result


def test_both_provider_adapters_request_the_fixed_schema(review_request):
    payload = json.dumps(valid_review())
    captured_openai = {}
    captured_anthropic = {}

    class Responses:
        def create(self, **kwargs):
            captured_openai.update(kwargs)
            return SimpleNamespace(output_text=payload)

    class Messages:
        def create(self, **kwargs):
            captured_anthropic.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=payload)])

    OpenAIHostileReviewer(
        SimpleNamespace(responses=Responses()), "openai-test",
    ).review(review_request)
    AnthropicHostileReviewer(
        SimpleNamespace(messages=Messages()), "anthropic-test",
    ).review(review_request)

    openai_schema = captured_openai["text"]["format"]["schema"]
    anthropic_schema = captured_anthropic["output_config"]["format"]["schema"]
    assert anthropic_schema["required"] == openai_schema["required"]
    assert set(anthropic_schema["properties"]) == set(openai_schema["properties"])
    assert "minimum" not in anthropic_schema["properties"]["confidence"]
    assert openai_schema["properties"]["confidence"]["minimum"] == 0


@pytest.mark.parametrize(
    "raw",
    [
        {"baseline": "", "sources": ["source"], "existing_solution_search": "x", "result": "x"},
        {"baseline": "x", "sources": [], "existing_solution_search": "x", "result": "x"},
        {"baseline": "x", "sources": "source", "existing_solution_search": "x", "result": "x"},
        {"baseline": "x", "sources": [{"uri": "source"}], "existing_solution_search": "x", "result": "x"},
        {"baseline": "x", "sources": ["source"], "existing_solution_search": "", "result": "x"},
        {
            "baseline": "x",
            "sources": ["source"],
            "existing_solution_search": "x",
            "result": "x",
            "state": "cemetery",
        },
    ],
)
def test_benchmark_adapter_fails_closed_on_malformed_provider_output(raw):
    provider = CallableBenchmarkProvider(lambda _: raw)
    request = BenchmarkRequest("hyp-1", 1, HypothesisRecord.seed("x").artifact)
    with pytest.raises(ValueError, match="incomplete contract"):
        provider.benchmark(request)


def test_repository_contract_allows_only_one_optimistic_writer():
    repository = InMemoryArtifactRepository()
    record = HypothesisRecord.seed("Optimistic concurrency")
    repository.save(record, expected_revision=None)

    changed_a = replace(record, revision=1, title="Writer A")
    changed_b = replace(record, revision=1, title="Writer B")

    def save(candidate):
        try:
            repository.save(candidate, expected_revision=0)
            return "saved"
        except ConcurrencyConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, (changed_a, changed_b)))

    assert sorted(results) == ["conflict", "saved"]
