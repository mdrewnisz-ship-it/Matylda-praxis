#!/usr/bin/env python3
"""Run the same three-scenario Praxis proof through one provider adapter."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from matylda_praxis.adapters.anthropic import AnthropicHostileReviewer
from matylda_praxis.adapters.codec import to_jsonable
from matylda_praxis.adapters.openai import OpenAIHostileReviewer
from matylda_praxis.integrations.execution_proof import run_execution_proof


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("openai", "anthropic"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort")
    parser.add_argument("--max-tokens", type=int, default=1600)
    parser.add_argument("--operator-id", help="Explicitly approves successful proof decisions.")
    parser.add_argument("--output")
    return parser.parse_args()


def reviewer_for(args: argparse.Namespace):
    if args.provider == "anthropic":
        from anthropic import Anthropic

        if not os.getenv("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is required")
        return AnthropicHostileReviewer(
            Anthropic(), args.model, max_tokens=args.max_tokens, effort=args.effort
        )
    from openai import OpenAI

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required")
    return OpenAIHostileReviewer(
        OpenAI(),
        args.model,
        max_output_tokens=args.max_tokens,
        reasoning_effort=args.effort,
    )


def main() -> int:
    args = parse_args()
    results = run_execution_proof(
        reviewer_for(args),
        operator_id=args.operator_id,
        channel="execution-proof",
    )
    payload = {
        "provider": args.provider,
        "model": args.model,
        "approved": args.operator_id is not None,
        "results": [to_jsonable(asdict(result)) for result in results],
    }
    rendered = json.dumps(payload, ensure_ascii=True, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if all(result.decision is not None for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
