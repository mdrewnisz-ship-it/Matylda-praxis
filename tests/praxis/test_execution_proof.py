from __future__ import annotations

import json

import pytest

from matylda_praxis.adapters.codec import record_to_json
from matylda_praxis.domain.models import HostileReviewDraft
from matylda_praxis.domain.types import ReviewRecommendation
from matylda_praxis.integrations.execution_proof import run_execution_proof


class ScriptedProviderReviewer:
    def __init__(self, provider: str) -> None:
        self.provider = provider

    def review(self, request):
        claim = request.artifact.claim
        if "generalizes" in claim:
            recommendation = ReviewRecommendation.REVISE
        elif "makes completion faster" in claim:
            recommendation = ReviewRecommendation.REJECT
        else:
            recommendation = ReviewRecommendation.TEST
        return HostileReviewDraft(
            strongest_objection="The strongest available alternative explanation was tested.",
            counterexample="The measured effect can disappear under the stated control.",
            hidden_assumptions=("Measurement stability is required.",),
            existing_solution_search="The named and adjacent solution classes were checked.",
            falsification_test="Run or inspect the direct controlled comparison.",
            minimum_evidence_required="One preregistered controlled result.",
            recommendation=recommendation,
            confidence=0.8,
        )


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_both_provider_hosts_execute_the_identical_proof_contract(provider):
    results = run_execution_proof(
        ScriptedProviderReviewer(provider),
        operator_id="proof-human",
        channel="provider-contract-test",
    )

    assert [item.recommendation for item in results] == ["TEST", "REVISE", "REJECT"]
    assert [item.decision for item in results] == ["TEST", "TEST", "REJECT"]
    assert all(item.approved for item in results)
    assert "artifact_deflated" in results[1].event_kinds
    assert results[2].record.memory_updates
    for result in results:
        serialized = record_to_json(result.record).casefold()
        assert "openai" not in serialized
        assert "anthropic" not in serialized


def test_failed_provider_recommendation_never_reaches_human_decision():
    class MismatchingReviewer(ScriptedProviderReviewer):
        def review(self, request):
            draft = super().review(request)
            if "generalizes" not in request.artifact.claim:
                return draft
            return HostileReviewDraft(
                strongest_objection=draft.strongest_objection,
                counterexample=draft.counterexample,
                hidden_assumptions=draft.hidden_assumptions,
                existing_solution_search=draft.existing_solution_search,
                falsification_test=draft.falsification_test,
                minimum_evidence_required=draft.minimum_evidence_required,
                recommendation=ReviewRecommendation.TEST,
                confidence=draft.confidence,
            )

    results = run_execution_proof(MismatchingReviewer("openai"), operator_id="proof-human")

    assert results[1].decision is None
    assert not results[1].approved
    assert results[1].record.decision_memos == ()
    assert "decision_recorded" not in results[1].event_kinds
