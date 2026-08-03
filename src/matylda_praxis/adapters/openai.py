"""OpenAI Responses API adapter for the hostile-review port."""

from __future__ import annotations

from typing import Any

from ..ports.interfaces import ReviewRequest
from .review_json import DARKROOM_SYSTEM, REVIEW_SCHEMA, parse_review, review_payload


class OpenAIHostileReviewer:
    def __init__(
        self,
        client: Any,
        model: str,
        *,
        max_output_tokens: int = 1600,
        reasoning_effort: str | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._reasoning_effort = reasoning_effort

    def review(self, request: ReviewRequest):
        arguments: dict[str, Any] = {
            "model": self._model,
            "instructions": DARKROOM_SYSTEM,
            "input": review_payload(request),
            "max_output_tokens": self._max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "hostile_review",
                    "strict": True,
                    "schema": REVIEW_SCHEMA,
                }
            },
        }
        if self._reasoning_effort is not None:
            arguments["reasoning"] = {"effort": self._reasoning_effort}
        response = self._client.responses.create(
            **arguments,
        )
        return parse_review(response.output_text)
