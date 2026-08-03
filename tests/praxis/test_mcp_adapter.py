from __future__ import annotations

from dataclasses import asdict

import pytest

from matylda_praxis.adapters.codec import record_from_json, record_to_json
from matylda_praxis.adapters.memory import InMemoryArtifactRepository
from matylda_praxis.application import ReferenceApplication
from matylda_praxis.integrations.mcp import ApprovalBoundary, PraxisMCPTools
from matylda_praxis.integrations.receipts import ExecutionReceipt, ReceiptStore
from matylda_praxis.protocol.errors import ApprovalDenied, ConcurrencyConflict, ProtocolViolation


def prepared_tools(reviewed_factory):
    record, _, _ = reviewed_factory()
    repository = InMemoryArtifactRepository()
    repository.save(record, expected_revision=None)
    application = ReferenceApplication(repository)
    boundary = ApprovalBoundary(application)
    return repository, record.id, PraxisMCPTools(application, boundary), boundary


def test_mcp_catalog_never_exposes_decision_execution(reviewed_factory):
    _, _, tools, _ = prepared_tools(reviewed_factory)
    names = {item["name"] for item in tools.manifest()}

    assert "propose_decision" in names
    assert "approve" not in names
    assert "decide" not in names
    assert all("approve" not in name for name in names)


def test_model_payload_cannot_forge_human_approval(reviewed_factory):
    repository, artifact_id, tools, _ = prepared_tools(reviewed_factory)
    before = repository.get(artifact_id)

    with pytest.raises(ValueError, match="host-owned"):
        tools.call("propose_decision", {
            "artifact_id": artifact_id,
            "proposal": {
                "decision": "TEST",
                "rationale": "Run the bounded test.",
                "confirmed_by_human": True,
                "operator_id": "model",
            },
        })

    assert repository.get(artifact_id) == before


def test_host_approval_is_single_use_and_audited(reviewed_factory):
    repository, artifact_id, tools, boundary = prepared_tools(reviewed_factory)
    proposal = tools.call("propose_decision", {
        "artifact_id": artifact_id,
        "proposal": {"decision": "TEST", "rationale": "Run the bounded test."},
    })

    memo = boundary.approve(
        proposal["proposal_id"], operator_id="human-1", channel="desktop"
    )

    assert memo.approval.operator_id == "human-1"
    assert memo.approval.channel == "desktop"
    assert len(repository.get(artifact_id).decision_memos) == 1
    with pytest.raises(ApprovalDenied, match="consumed"):
        boundary.approve(
            proposal["proposal_id"], operator_id="human-1", channel="desktop"
        )


def test_denial_and_stale_proposal_leave_no_partial_decision(reviewed_factory):
    repository, artifact_id, tools, boundary = prepared_tools(reviewed_factory)
    denied = tools.call("propose_decision", {
        "artifact_id": artifact_id,
        "proposal": {"decision": "TEST", "rationale": "First proposal."},
    })
    boundary.deny(denied["proposal_id"])
    assert repository.get(artifact_id).decision_memos == ()

    stale = tools.call("propose_decision", {
        "artifact_id": artifact_id,
        "proposal": {"decision": "TEST", "rationale": "Second proposal."},
    })
    tools.call("record_benchmark", {
        "artifact_id": artifact_id,
        "benchmark": {
            "baseline": "A newer null baseline.",
            "sources": ["source:new"],
            "existing_solution_search": "A newer bounded search.",
            "result": "No equivalent result found.",
        },
    })

    with pytest.raises(ConcurrencyConflict, match="stale"):
        boundary.approve(
            stale["proposal_id"], operator_id="human-1", channel="desktop"
        )
    assert repository.get(artifact_id).decision_memos == ()


def test_mcp_review_cannot_bypass_exact_benchmark_binding(reviewed_factory, review_factory):
    repository, artifact_id, tools, _ = prepared_tools(reviewed_factory)
    before = repository.get(artifact_id)
    payload = asdict(review_factory())
    payload["recommendation"] = payload["recommendation"].value
    payload["hidden_assumptions"] = list(payload["hidden_assumptions"])
    payload["benchmark_id"] = "bench-from-another-run"

    with pytest.raises(ProtocolViolation, match="exact current-version benchmark"):
        tools.call("record_review", {"artifact_id": artifact_id, "review": payload})

    assert repository.get(artifact_id) == before


def test_execution_receipt_is_deletable_without_affecting_domain_record(
    tmp_path, reviewed_factory
):
    record, _, _ = reviewed_factory()
    serialized = record_to_json(record)
    store = ReceiptStore(tmp_path / "receipts.jsonl")
    store.append(ExecutionReceipt(
        artifact_id=record.id,
        provider="test-provider",
        model="test-model",
        prompt_hash="abc123",
        input_tokens=10,
        output_tokens=5,
        latency_seconds=0.1,
    ))
    assert len(store.list()) == 1

    store.path.unlink()

    assert record_from_json(serialized) == record
