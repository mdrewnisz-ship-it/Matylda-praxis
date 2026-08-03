"""Adapter for deterministic or externally supplied benchmark functions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Mapping

from ..ports.interfaces import BenchmarkDraft, BenchmarkRequest


class CallableBenchmarkProvider:
    def __init__(self, run: Callable[[BenchmarkRequest], Mapping[str, Any]]) -> None:
        self._run = run

    def benchmark(self, request: BenchmarkRequest) -> BenchmarkDraft:
        raw = self._run(request)
        expected = {"baseline", "sources", "existing_solution_search", "result"}
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise ValueError("Benchmark provider returned an incomplete contract")
        raw_sources = raw.get("sources", ())
        if not isinstance(raw_sources, (list, tuple)) or any(
            not isinstance(item, str) for item in raw_sources
        ):
            raise ValueError("Benchmark provider returned an incomplete contract")
        text_fields = ("baseline", "existing_solution_search", "result")
        if any(not isinstance(raw[field], str) for field in text_fields):
            raise ValueError("Benchmark provider returned an incomplete contract")
        sources = tuple(item.strip() for item in raw_sources if item.strip())
        draft = BenchmarkDraft(
            baseline=raw["baseline"].strip(),
            sources=sources,
            existing_solution_search=raw["existing_solution_search"].strip(),
            result=raw["result"].strip(),
        )
        if not all((draft.baseline, draft.sources, draft.existing_solution_search, draft.result)):
            raise ValueError("Benchmark provider returned an incomplete contract")
        return draft
