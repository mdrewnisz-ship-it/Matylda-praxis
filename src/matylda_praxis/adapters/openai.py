"""OpenAI Responses API adapter for the hostile-review port."""

from __future__ import annotations

from typing import Any

from ..ports.interfaces import ReviewRequest
from .review_json import DARKROOM_SYSTEM, REVIEW_SCHEMA, parse_review, review_payload


class OpenAIHostileReviewer:
    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    def review(self, request: ReviewRequest):
        response = self._client.responses.create(
            model=self._model,
            instructions=DARKROOM_SYSTEM,
            input=review_payload(request),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "hostile_review",
                    "strict": True,
                    "schema": REVIEW_SCHEMA,
                }
            },
        )
        return parse_review(response.output_text)
