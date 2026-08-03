"""Anthropic Messages API adapter for the hostile-review port."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..ports.interfaces import ReviewRequest
from .review_json import DARKROOM_SYSTEM, REVIEW_SCHEMA, parse_review, review_payload


# Anthropic Structured Outputs accepts a JSON Schema subset without numeric
# bounds. The shared parser still enforces confidence in the closed 0..1 range.
ANTHROPIC_REVIEW_SCHEMA = deepcopy(REVIEW_SCHEMA)
ANTHROPIC_REVIEW_SCHEMA["properties"]["confidence"].pop("minimum")
ANTHROPIC_REVIEW_SCHEMA["properties"]["confidence"].pop("maximum")


class AnthropicHostileReviewer:
    def __init__(
        self,
        client: Any,
        model: str,
        *,
        max_tokens: int = 1600,
        effort: str | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._effort = effort

    def review(self, request: ReviewRequest):
        output_config: dict[str, Any] = {
            "format": {
                "type": "json_schema",
                "schema": ANTHROPIC_REVIEW_SCHEMA,
            }
        }
        if self._effort is not None:
            output_config["effort"] = self._effort
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=DARKROOM_SYSTEM,
            messages=[{"role": "user", "content": review_payload(request)}],
            output_config=output_config,
        )
        text = "".join(
            block.text for block in response.content
            if getattr(block, "type", None) == "text"
        )
        return parse_review(text)
