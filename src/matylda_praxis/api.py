"""Minimal local HTTP JSON transport for the reference application."""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from .adapters.codec import record_to_dict, to_jsonable
from .adapters.sqlite import SQLiteArtifactRepository
from .application import ReferenceApplication
from .protocol.errors import ConcurrencyConflict, ProtocolViolation

MAX_BODY_BYTES = 1_000_000


def _record(record):
    return record_to_dict(record)["record"]


def _item(value):
    return to_jsonable(asdict(value))


class ReferenceAPI:
    def __init__(self, application: ReferenceApplication) -> None:
        self.application = application

    def dispatch(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            segments = [unquote(item) for item in urlsplit(path).path.split("/") if item]
            data = body or {}
            if method == "GET" and segments == ["health"]:
                return 200, {"ok": True, "service": "matylda-praxis", "schema_version": 1}
            if segments == ["hypotheses"]:
                if method == "GET":
                    return 200, {
                        "ok": True,
                        "hypotheses": [_record(item) for item in self.application.list()],
                    }
                if method == "POST":
                    title = data.get("title")
                    if not isinstance(title, str):
                        raise ValueError("title is required text")
                    return 201, {"ok": True, "hypothesis": _record(self.application.create(title))}
            if len(segments) >= 2 and segments[0] == "hypotheses":
                artifact_id = segments[1]
                if method == "GET" and len(segments) == 2:
                    return 200, {"ok": True, "hypothesis": _record(self.application.get(artifact_id))}
                if method == "POST" and len(segments) == 3:
                    action = segments[2]
                    if action == "advance":
                        result = self.application.advance(
                            artifact_id,
                            str(data.get("state", "")),
                            data.get("artifact"),
                        )
                        return 200, {"ok": True, "hypothesis": _record(result)}
                    if action == "preflight":
                        return 200, {"ok": True, "preflight": _item(self.application.preflight(artifact_id))}
                    if action == "benchmark":
                        return 200, {"ok": True, "benchmark": _item(self.application.benchmark(artifact_id, data))}
                    if action == "review":
                        return 200, {"ok": True, "review": _item(self.application.review(artifact_id, data))}
                    if action == "deflate":
                        return 200, {"ok": True, "deflation": _item(self.application.deflate(artifact_id, data))}
                    if action == "decision":
                        decision = str(data.get("decision", ""))
                        decision_data = dict(data)
                        decision_data.pop("decision", None)
                        return 200, {
                            "ok": True,
                            "decision": _item(self.application.decide(
                                artifact_id, decision, decision_data,
                            )),
                        }
                    if action == "resume":
                        return 201, {"ok": True, "hypothesis": _record(self.application.resume(artifact_id, data))}
            return 404, {"ok": False, "error": "route not found"}
        except KeyError as exc:
            return 404, {"ok": False, "error": str(exc)}
        except ConcurrencyConflict as exc:
            return 409, {"ok": False, "error": str(exc)}
        except (ProtocolViolation, TypeError, ValueError) as exc:
            return 400, {"ok": False, "error": str(exc)}


def make_server(
    database: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
) -> ThreadingHTTPServer:
    api = ReferenceAPI(ReferenceApplication(SQLiteArtifactRepository(database)))

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, method: str) -> None:
            body: Mapping[str, Any] | None = None
            if method == "POST":
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_BODY_BYTES:
                    self.send_error(413, "request body too large")
                    return
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    decoded = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    decoded = None
                if not isinstance(decoded, Mapping):
                    status, payload = 400, {"ok": False, "error": "body must be a JSON object"}
                    self._write(status, payload)
                    return
                body = decoded
            status, payload = api.dispatch(method, self.path, body)
            self._write(status, payload)

        def _write(self, status: int, payload: Mapping[str, Any]) -> None:
            encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            self._respond("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._respond("POST")

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def serve(database: str, *, host: str = "127.0.0.1", port: int = 8787) -> None:
    server = make_server(database, host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
