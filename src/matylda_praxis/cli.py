"""Command-line reference interface for Matylda Praxis."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .adapters.codec import record_to_dict, to_jsonable
from .adapters.sqlite import SQLiteArtifactRepository
from .api import serve
from .application import ReferenceApplication
from .migration import migrate_legacy_registry
from .protocol.errors import ConcurrencyConflict

DEFAULT_DATABASE = os.environ.get("MATYLDA_PRAXIS_DB", ".praxis/praxis.db")


def _load_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    return data


def _output(value: Any) -> None:
    if hasattr(value, "versions") and hasattr(value, "decision_memos"):
        value = record_to_dict(value)["record"]
    elif is_dataclass(value):
        value = to_jsonable(asdict(value))
    elif isinstance(value, tuple) and all(
        hasattr(item, "versions") for item in value
    ):
        value = [record_to_dict(item)["record"] for item in value]
    elif isinstance(value, Enum):
        value = value.value
    print(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="matylda-praxis",
        description="Portable executable epistemic protocol",
    )
    parser.add_argument("--db", default=DEFAULT_DATABASE, help="SQLite database path")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="capture a cheap seed")
    create.add_argument("title")

    commands.add_parser("list", help="list hypothesis records")
    show = commands.add_parser("show", help="show one hypothesis record")
    show.add_argument("artifact_id")

    advance = commands.add_parser("advance", help="advance an early lifecycle state")
    advance.add_argument("artifact_id")
    advance.add_argument("state", choices=["incubator", "exploration", "working"])
    advance.add_argument("--input", help="working artifact JSON file, or - for stdin")

    preflight = commands.add_parser("preflight", help="run deterministic preflight")
    preflight.add_argument("artifact_id")

    for name in ("benchmark", "review", "deflate", "decide", "resume"):
        command = commands.add_parser(name)
        command.add_argument("artifact_id")
        if name == "decide":
            command.add_argument("decision", choices=["TEST", "WAIT", "REJECT", "PUBLISH"])
        command.add_argument("--input", required=True, help="JSON file, or - for stdin")

    migration = commands.add_parser("import-lab", help="selectively import Lab records")
    migration.add_argument("source", help="Matylda Lab hypotheses.json")
    migration.add_argument("--id", action="append", required=True, dest="record_ids")
    migration.add_argument(
        "--apply",
        action="store_true",
        help="write records; without this flag the command is a dry run",
    )

    server = commands.add_parser("serve", help="run the local reference HTTP API")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8787)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            try:
                serve(args.db, host=args.host, port=args.port)
            except KeyboardInterrupt:
                return 0
            return 0
        repository = SQLiteArtifactRepository(args.db)
        if args.command == "import-lab":
            report = migrate_legacy_registry(
                args.source,
                repository,
                args.record_ids,
                dry_run=not args.apply,
            )
            _output(report)
            return 0 if report.ok else 2
        application = ReferenceApplication(repository)
        if args.command == "create":
            result = application.create(args.title)
        elif args.command == "list":
            result = application.list()
        elif args.command == "show":
            result = application.get(args.artifact_id)
        elif args.command == "advance":
            result = application.advance(
                args.artifact_id,
                args.state,
                _load_json(args.input) if args.input else None,
            )
        elif args.command == "preflight":
            result = application.preflight(args.artifact_id)
        elif args.command == "benchmark":
            result = application.benchmark(args.artifact_id, _load_json(args.input))
        elif args.command == "review":
            result = application.review(args.artifact_id, _load_json(args.input))
        elif args.command == "deflate":
            result = application.deflate(args.artifact_id, _load_json(args.input))
        elif args.command == "decide":
            result = application.decide(
                args.artifact_id,
                args.decision,
                _load_json(args.input),
            )
        elif args.command == "resume":
            result = application.resume(args.artifact_id, _load_json(args.input))
        else:
            parser.error("unknown command")
            return 2
        _output(result)
        return 0
    except ConcurrencyConflict as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 3
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
