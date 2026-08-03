"""Approval-safe, provider-neutral MCP tool surface for Praxis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import Lock
from typing import Any, Callable, Mapping
from uuid import uuid4

from ..adapters.codec import to_jsonable
from ..application import ReferenceApplication
from ..domain.types import DecisionType, RejectionReason
from ..protocol.errors import ApprovalDenied, ConcurrencyConflict


class ToolClass(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE_MUTATION = "reversible_mutation"
    CONSEQUENTIAL_PROPOSAL = "consequential_proposal"


@dataclass(frozen=True, slots=True)
class ToolDescription:
    name: str
    classification: ToolClass
    description: str


@dataclass(frozen=True, slots=True)
class _DecisionProposal:
    proposal_id: str
    artifact_id: str
    expected_revision: int
    decision: DecisionType
    rationale: str
    reason_code: RejectionReason | None
    reentry_condition: str | None
    review_date: str | None
    publication_target: str | None
    expires_at: datetime


def _dump(value: Any) -> Any:
    return to_jsonable(asdict(value))


class ApprovalBoundary:
    """Host-only approval boundary; this object is never registered as an MCP tool."""

    def __init__(self, application: ReferenceApplication, *, ttl_seconds: int = 900) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        self._application = application
        self._ttl = timedelta(seconds=ttl_seconds)
        self._proposals: dict[str, _DecisionProposal] = {}
        self._lock = Lock()

    def propose(self, artifact_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        forbidden = {"confirmed_by_human", "operator_id", "channel"} & set(payload)
        if forbidden:
            raise ValueError("Approval evidence is host-owned and cannot be proposed")
        allowed = {
            "decision",
            "rationale",
            "reason_code",
            "reentry_condition",
            "review_date",
            "publication_target",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"Unknown proposal fields: {', '.join(sorted(unknown))}")
        decision = DecisionType(str(payload.get("decision", "")).upper())
        rationale = str(payload.get("rationale", "")).strip()
        if not rationale:
            raise ValueError("rationale is required")
        raw_reason = payload.get("reason_code")
        reason = RejectionReason(str(raw_reason).upper()) if raw_reason else None
        record = self._application.get(artifact_id)
        proposal = _DecisionProposal(
            proposal_id=f"proposal_{uuid4().hex}",
            artifact_id=artifact_id,
            expected_revision=record.revision,
            decision=decision,
            rationale=rationale,
            reason_code=reason,
            reentry_condition=_optional_text(payload.get("reentry_condition")),
            review_date=_optional_text(payload.get("review_date")),
            publication_target=_optional_text(payload.get("publication_target")),
            expires_at=datetime.now(timezone.utc) + self._ttl,
        )
        with self._lock:
            self._proposals[proposal.proposal_id] = proposal
        return {
            "proposal_id": proposal.proposal_id,
            "artifact_id": artifact_id,
            "expected_revision": proposal.expected_revision,
            "decision": decision.value,
            "expires_at": proposal.expires_at.isoformat(),
            "status": "AWAITING_HUMAN_APPROVAL",
        }

    def approve(self, proposal_id: str, *, operator_id: str, channel: str) -> Any:
        operator_id = operator_id.strip()
        channel = channel.strip()
        if not operator_id or not channel:
            raise ApprovalDenied("Explicit operator identity and channel are required")
        proposal = self._consume(proposal_id)
        if proposal.expires_at <= datetime.now(timezone.utc):
            raise ApprovalDenied("Decision proposal expired")
        current = self._application.get(proposal.artifact_id)
        if current.revision != proposal.expected_revision:
            raise ConcurrencyConflict("Decision proposal is stale")
        payload = {
            "confirmed_by_human": True,
            "operator_id": operator_id,
            "channel": channel,
            "rationale": proposal.rationale,
            "reason_code": proposal.reason_code.value if proposal.reason_code else None,
            "reentry_condition": proposal.reentry_condition,
            "review_date": proposal.review_date,
            "publication_target": proposal.publication_target,
        }
        return self._application.decide(
            proposal.artifact_id,
            proposal.decision.value,
            payload,
        )

    def deny(self, proposal_id: str) -> None:
        self._consume(proposal_id)

    def _consume(self, proposal_id: str) -> _DecisionProposal:
        with self._lock:
            proposal = self._proposals.pop(proposal_id, None)
        if proposal is None:
            raise ApprovalDenied("Unknown or already consumed decision proposal")
        return proposal


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


class PraxisMCPTools:
    """In-process contract that can be mounted on any conforming MCP transport."""

    DESCRIPTIONS = (
        ToolDescription("list_artifacts", ToolClass.READ_ONLY, "List Praxis records."),
        ToolDescription("get_artifact", ToolClass.READ_ONLY, "Read one Praxis record."),
        ToolDescription("capture_seed", ToolClass.REVERSIBLE_MUTATION, "Capture a new seed."),
        ToolDescription("advance_artifact", ToolClass.REVERSIBLE_MUTATION, "Advance an early state."),
        ToolDescription("run_preflight", ToolClass.REVERSIBLE_MUTATION, "Run deterministic preflight."),
        ToolDescription("record_benchmark", ToolClass.REVERSIBLE_MUTATION, "Record benchmark evidence."),
        ToolDescription("record_review", ToolClass.REVERSIBLE_MUTATION, "Record hostile review output."),
        ToolDescription("deflate_artifact", ToolClass.REVERSIBLE_MUTATION, "Narrow a reviewed artifact."),
        ToolDescription("propose_decision", ToolClass.CONSEQUENTIAL_PROPOSAL, "Propose, but never approve, a decision."),
    )

    def __init__(self, application: ReferenceApplication, approval: ApprovalBoundary | None = None) -> None:
        self.application = application
        self.approval = approval or ApprovalBoundary(application)
        self._handlers: dict[str, Callable[[Mapping[str, Any]], Any]] = {
            "list_artifacts": lambda _: [_dump(item) for item in self.application.list()],
            "get_artifact": lambda p: _dump(self.application.get(str(p["artifact_id"]))),
            "capture_seed": lambda p: _dump(self.application.create(str(p["title"]))),
            "advance_artifact": lambda p: _dump(self.application.advance(
                str(p["artifact_id"]), str(p["state"]), p.get("artifact")
            )),
            "run_preflight": lambda p: _dump(self.application.preflight(str(p["artifact_id"]))),
            "record_benchmark": lambda p: _dump(self.application.benchmark(
                str(p["artifact_id"]), _mapping(p.get("benchmark"), "benchmark")
            )),
            "record_review": lambda p: _dump(self.application.review(
                str(p["artifact_id"]), _mapping(p.get("review"), "review")
            )),
            "deflate_artifact": lambda p: _dump(self.application.deflate(
                str(p["artifact_id"]), _mapping(p.get("deflation"), "deflation")
            )),
            "propose_decision": lambda p: self.approval.propose(
                str(p["artifact_id"]), _mapping(p.get("proposal"), "proposal")
            ),
        }

    def manifest(self) -> tuple[dict[str, str], ...]:
        return tuple({
            "name": item.name,
            "classification": item.classification.value,
            "description": item.description,
        } for item in self.DESCRIPTIONS)

    def call(self, name: str, payload: Mapping[str, Any] | None = None) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            raise KeyError(f"Unknown Praxis MCP tool: {name}")
        return handler(payload or {})


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def build_fastmcp(tools: PraxisMCPTools):
    """Mount the contract on the optional official MCP Python SDK."""
    try:
        try:
            from mcp.server.mcpserver import MCPServer as Server
        except ImportError:
            from mcp.server.fastmcp import FastMCP as Server
    except ImportError as exc:
        raise RuntimeError("Install matylda-praxis[mcp] to serve the MCP adapter") from exc

    try:
        server = Server("matylda-praxis", title="Matylda Praxis")
    except TypeError:  # MCP SDK 1.x
        server = Server("Matylda Praxis")
    for item in tools.DESCRIPTIONS:
        def make_invoke(tool_name: str):
            def invoke(payload: dict[str, Any] | None = None) -> Any:
                return tools.call(tool_name, payload)

            return invoke

        name = item.name
        invoke = make_invoke(name)
        invoke.__name__ = name
        invoke.__doc__ = item.description
        server.tool(name=name)(invoke)
    return server


def main() -> None:
    """Serve the local adapter over stdio; no network listener is opened."""
    import argparse

    from ..adapters.sqlite import SQLiteArtifactRepository

    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default=".praxis/praxis.db")
    args = parser.parse_args()
    application = ReferenceApplication(SQLiteArtifactRepository(args.database))
    build_fastmcp(PraxisMCPTools(application)).run(transport="stdio")
