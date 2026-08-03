"""Provider-neutral end-to-end proof scenarios for execution substrates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..adapters.memory import InMemoryArtifactRepository
from ..application import ReferenceApplication
from ..domain.models import HostileReviewDraft
from ..domain.types import DecisionType, RejectionReason, ReviewRecommendation
from ..ports.interfaces import HostileReviewer, ReviewRequest
from .mcp import ApprovalBoundary, PraxisMCPTools


@dataclass(frozen=True, slots=True)
class ProofScenario:
    name: str
    artifact: dict[str, Any]
    benchmark: dict[str, Any]
    expected_recommendation: ReviewRecommendation
    decision: DecisionType
    decision_fields: dict[str, Any]
    deflation: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ProofResult:
    scenario: str
    recommendation: str
    decision: str | None
    approved: bool
    event_kinds: tuple[str, ...]
    record: Any


PROOF_SCENARIOS = (
    ProofScenario(
        name="bounded-test",
        artifact={
            "claim": "A bounded interface change may reduce one measured omission rate.",
            "scope": "One preregistered controlled pilot.",
            "assumptions": ["Event logging is stable."],
            "evidence_for": ["A small pilot produced the directional signal."],
            "evidence_against": ["The pilot had no control group."],
            "falsification_condition": "The controlled effect is zero or reverses.",
            "next_test": "Run the preregistered controlled pilot.",
            "exploration_cost": "2 days",
        },
        benchmark={
            "baseline": "The null baseline predicts no difference.",
            "sources": ["proof:bounded-baseline"],
            "existing_solution_search": "The workflow and two adjacent terms were checked.",
            "result": "No equivalent result was found.",
        },
        expected_recommendation=ReviewRecommendation.TEST,
        decision=DecisionType.TEST,
        decision_fields={"rationale": "Run the bounded preregistered test."},
    ),
    ProofScenario(
        name="repairable-revise",
        artifact={
            "claim": "The pilot effect generalizes to all comparable workflows.",
            "scope": "One observational pilot used to motivate a bounded replication.",
            "assumptions": ["The observed sample is representative."],
            "evidence_for": ["One observational pilot showed an effect."],
            "evidence_against": ["Assignment was not randomized."],
            "falsification_condition": "The effect disappears under random assignment.",
            "next_test": "Run one randomized replication.",
            "exploration_cost": "2 days",
        },
        benchmark={
            "baseline": "Selection bias can reproduce the observed effect.",
            "sources": ["proof:selection-bias"],
            "existing_solution_search": "The broad claim and two narrower variants were checked.",
            "result": "The broad claim exceeds the available evidence.",
        },
        expected_recommendation=ReviewRecommendation.REVISE,
        decision=DecisionType.TEST,
        decision_fields={"rationale": "Test the narrowed candidate."},
        deflation={
            "changes": {"claim": "A bounded randomized replication may reproduce the pilot effect."},
            "withdrawn_claims": ["The effect generalizes to all comparable workflows."],
            "rationale": "Removed the unsupported generalization before testing.",
        },
    ),
    ProofScenario(
        name="terminal-reject",
        artifact={
            "claim": "Animated guidance makes completion faster.",
            "scope": "The measured workflow in the completed controlled comparison.",
            "assumptions": ["Completion time is measured correctly."],
            "evidence_for": ["Participants reported greater clarity."],
            "evidence_against": ["Instrumented sessions were 18 percent slower."],
            "falsification_condition": "No completion-time improvement is observed.",
            "next_test": "Audit the completed timing comparison.",
            "exploration_cost": "30 min",
        },
        benchmark={
            "baseline": "The completed controlled comparison is the direct baseline.",
            "sources": ["proof:timing-comparison"],
            "existing_solution_search": "No external proxy is needed for the direct measurement.",
            "result": "The measured result contradicts the directional claim.",
        },
        expected_recommendation=ReviewRecommendation.REJECT,
        decision=DecisionType.REJECT,
        decision_fields={
            "rationale": "The direct result meets the falsification condition.",
            "reason_code": RejectionReason.FALSIFIED.value,
        },
    ),
)


def run_scenario(
    scenario: ProofScenario,
    reviewer: HostileReviewer,
    *,
    operator_id: str | None = None,
    channel: str = "execution-proof",
) -> ProofResult:
    repository = InMemoryArtifactRepository()
    application = ReferenceApplication(repository)
    approval = ApprovalBoundary(application)
    tools = PraxisMCPTools(application, approval)

    record = tools.call("capture_seed", {"title": f"Execution proof: {scenario.name}"})
    artifact_id = record["id"]
    tools.call("advance_artifact", {"artifact_id": artifact_id, "state": "incubator"})
    tools.call("advance_artifact", {"artifact_id": artifact_id, "state": "exploration"})
    tools.call("advance_artifact", {
        "artifact_id": artifact_id,
        "state": "working",
        "artifact": scenario.artifact,
    })
    preflight = tools.call("run_preflight", {"artifact_id": artifact_id})
    if not preflight["issues"] == []:
        raise AssertionError(f"Proof preflight failed: {preflight['issues']}")
    benchmark = tools.call("record_benchmark", {
        "artifact_id": artifact_id,
        "benchmark": scenario.benchmark,
    })
    current = application.get(artifact_id)
    draft = reviewer.review(ReviewRequest(
        artifact_id,
        current.current.number,
        current.artifact,
        current.benchmark_results[-1],
    ))
    review_payload = asdict(draft)
    review_payload["recommendation"] = draft.recommendation.value
    review_payload["hidden_assumptions"] = list(draft.hidden_assumptions)
    review_payload["benchmark_id"] = benchmark["benchmark_id"]
    tools.call("record_review", {"artifact_id": artifact_id, "review": review_payload})

    if draft.recommendation is not scenario.expected_recommendation:
        final = application.get(artifact_id)
        return ProofResult(
            scenario.name,
            draft.recommendation.value,
            None,
            False,
            tuple(event.kind for event in final.events),
            final,
        )
    if scenario.deflation is not None:
        tools.call("deflate_artifact", {
            "artifact_id": artifact_id,
            "deflation": scenario.deflation,
        })
    proposal_payload = {"decision": scenario.decision.value, **scenario.decision_fields}
    proposal = tools.call("propose_decision", {
        "artifact_id": artifact_id,
        "proposal": proposal_payload,
    })
    approved = operator_id is not None
    if approved:
        approval.approve(proposal["proposal_id"], operator_id=operator_id, channel=channel)
    final = application.get(artifact_id)
    return ProofResult(
        scenario.name,
        draft.recommendation.value,
        final.disposition.value if final.disposition else None,
        approved,
        tuple(event.kind for event in final.events),
        final,
    )


def run_execution_proof(
    reviewer: HostileReviewer,
    *,
    operator_id: str | None = None,
    channel: str = "execution-proof",
) -> tuple[ProofResult, ...]:
    return tuple(
        run_scenario(
            scenario,
            reviewer,
            operator_id=operator_id,
            channel=channel,
        )
        for scenario in PROOF_SCENARIOS
    )
