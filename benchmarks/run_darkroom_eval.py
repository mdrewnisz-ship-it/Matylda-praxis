#!/usr/bin/env python3
"""Run the frozen DARKROOM pilot against the production provider adapters."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from matylda_praxis.adapters.anthropic import AnthropicHostileReviewer
from matylda_praxis.adapters.openai import OpenAIHostileReviewer
from matylda_praxis.domain.models import BenchmarkResult, HypothesisArtifact
from matylda_praxis.evaluation import (
    EvaluationExpectation,
    estimate_token_cost,
    failed_result,
    score_review,
    summarize,
)
from matylda_praxis.ports.interfaces import ReviewRequest


class Capture:
    def __init__(self, endpoint: Any) -> None:
        self._endpoint = endpoint
        self.response: Any = None

    def create(self, **kwargs: Any) -> Any:
        self.response = self._endpoint.create(**kwargs)
        return self.response


def load_suite(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("evaluation suite must contain a cases list")
    return payload


def build_request(case: dict[str, Any]) -> ReviewRequest:
    artifact = case["artifact"]
    benchmark = case["benchmark"]
    return ReviewRequest(
        artifact_id=f"eval-{case['id']}",
        artifact_version=1,
        artifact=HypothesisArtifact(
            claim=artifact["claim"],
            scope=artifact["scope"],
            assumptions=tuple(artifact["assumptions"]),
            evidence_for=tuple(artifact["evidence_for"]),
            evidence_against=tuple(artifact["evidence_against"]),
            falsification_condition=artifact["falsification_condition"],
            next_test=artifact["next_test"],
            exploration_cost=artifact["exploration_cost"],
        ),
        benchmark=BenchmarkResult(
            benchmark_id=f"bench-{case['id']}",
            artifact_version=1,
            baseline=benchmark["baseline"],
            sources=tuple(benchmark["sources"]),
            existing_solution_search=benchmark["existing_solution_search"],
            result=benchmark["result"],
        ),
    )


def extract_text(provider: str, response: Any) -> str:
    if response is None:
        return ""
    if provider == "anthropic":
        return "".join(
            block.text for block in response.content
            if getattr(block, "type", None) == "text"
        )
    return str(getattr(response, "output_text", ""))


def extract_usage(provider: str, response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    if provider == "anthropic":
        return int(usage.input_tokens), int(usage.output_tokens)
    return int(usage.input_tokens), int(usage.output_tokens)


def make_reviewer(provider: str, model: str, max_tokens: int):
    if provider == "anthropic":
        import anthropic

        capture = Capture(anthropic.Anthropic().messages)
        reviewer = AnthropicHostileReviewer(
            SimpleNamespace(messages=capture), model, max_tokens=max_tokens,
        )
        return reviewer, capture
    if provider == "openai":
        import openai

        capture = Capture(openai.OpenAI().responses)
        reviewer = OpenAIHostileReviewer(SimpleNamespace(responses=capture), model)
        return reviewer, capture
    raise ValueError(f"unsupported provider: {provider}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("anthropic", "openai"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--suite", type=Path, default=ROOT / "benchmarks/darkroom_v1.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="run only this case id; may be supplied more than once",
    )
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--max-tokens", type=int, default=1600)
    parser.add_argument("--input-price", type=float, required=True, help="USD per million tokens")
    parser.add_argument("--output-price", type=float, required=True, help="USD per million tokens")
    args = parser.parse_args()

    key_name = "ANTHROPIC_API_KEY" if args.provider == "anthropic" else "OPENAI_API_KEY"
    if not os.environ.get(key_name):
        parser.error(f"{key_name} is not set")
    suite = load_suite(args.suite)
    cases = suite["cases"]
    if args.case_ids:
        requested = set(args.case_ids)
        cases = [case for case in cases if case["id"] in requested]
        missing = requested - {case["id"] for case in cases}
        if missing:
            parser.error(f"unknown case ids: {', '.join(sorted(missing))}")
    cases = cases[:args.max_cases]
    results = []
    for case in cases:
        expectation = EvaluationExpectation(
            recommendations=tuple(case["expected_recommendations"]),
            objection_concepts=tuple(
                tuple(group) for group in case["objection_concepts"]
            ),
        )
        reviewer, capture = make_reviewer(args.provider, args.model, args.max_tokens)
        started = time.monotonic()
        raw_review = ""
        try:
            review = reviewer.review(build_request(case))
            latency = time.monotonic() - started
            raw_review = extract_text(args.provider, capture.response)
            input_tokens, output_tokens = extract_usage(args.provider, capture.response)
            cost = estimate_token_cost(
                input_tokens,
                output_tokens,
                input_usd_per_million=args.input_price,
                output_usd_per_million=args.output_price,
            )
            result = score_review(
                case["id"], review, expectation,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_seconds=latency,
                estimated_cost_usd=cost,
                raw_review=raw_review,
            )
        except Exception as exc:
            latency = time.monotonic() - started
            raw_review = extract_text(args.provider, capture.response)
            input_tokens, output_tokens = extract_usage(args.provider, capture.response)
            cost = estimate_token_cost(
                input_tokens,
                output_tokens,
                input_usd_per_million=args.input_price,
                output_usd_per_million=args.output_price,
            )
            result = failed_result(
                case["id"], expectation,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_seconds=latency,
                estimated_cost_usd=cost,
                raw_review=raw_review,
                error=f"{type(exc).__name__}: {exc}",
            )
        results.append(result)
        print(
            f"{case['id']}: contract={result.contract_valid} "
            f"recommendation={result.recommendation or '-'} "
            f"concepts={result.concept_hits}/{result.concept_total}",
            flush=True,
        )

    report = {
        "suite": suite["suite"],
        "provider": args.provider,
        "model": args.model,
        "input_usd_per_million": args.input_price,
        "output_usd_per_million": args.output_price,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summarize(results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=True))
    return 0 if all(item.contract_valid for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
