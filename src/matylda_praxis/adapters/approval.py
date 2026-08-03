"""Explicit local approval adapter; no model can approve its own decision."""

from __future__ import annotations

from collections.abc import Callable

from ..domain.models import ApprovalEvidence
from ..ports.interfaces import DecisionRequest


class CallbackHumanApproval:
    def __init__(
        self,
        operator_id: str,
        confirm: Callable[[DecisionRequest], bool],
        *,
        channel: str = "local",
    ) -> None:
        self._operator_id = operator_id.strip()
        self._channel = channel.strip()
        self._confirm = confirm
        if not self._operator_id or not self._channel:
            raise ValueError("operator_id and channel are required")

    def approve(self, request: DecisionRequest) -> ApprovalEvidence | None:
        if self._confirm(request) is not True:
            return None
        return ApprovalEvidence(self._operator_id, self._channel)
