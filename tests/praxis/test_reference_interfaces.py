from __future__ import annotations

import json
from dataclasses import replace

from matylda_praxis.adapters.sqlite import SQLiteArtifactRepository
from matylda_praxis.api import ReferenceAPI, load_static_asset
from matylda_praxis.application import ReferenceApplication
from matylda_praxis.cli import build_parser, main


ARTIFACT = {
    "claim": "A pilot effect is measurable.",
    "scope": "One pilot sample.",
    "assumptions": ["Measurement is stable."],
    "evidence_for": ["Pilot observation."],
    "evidence_against": [],
    "falsification_condition": "No effect in control.",
    "next_test": "Controlled comparison.",
    "exploration_cost": "30 min",
}

BENCHMARK = {
    "baseline": "The null model predicts no effect.",
    "sources": ["source:api"],
    "existing_solution_search": "Index and two synonyms checked.",
    "result": "No equivalent result found.",
}

REVIEW = {
    "strongest_objection": "Selection bias may explain the effect.",
    "counterexample": "The effect disappears after randomization.",
    "hidden_assumptions": ["The sample is representative."],
    "existing_solution_search": "One adjacent term remains unchecked.",
    "falsification_test": "Randomize assignment.",
    "minimum_evidence_required": "One controlled replication.",
    "recommendation": "TEST",
    "confidence": 0.74,
}


def api_for(path):
    return ReferenceAPI(ReferenceApplication(SQLiteArtifactRepository(path)))


def test_gui_assets_are_packaged_and_use_the_json_transport():
    index, index_type = load_static_asset("/")
    script, script_type = load_static_asset("/app.js?version=test")
    stylesheet, stylesheet_type = load_static_asset("/app.css")

    assert index_type == "text/html; charset=utf-8"
    assert script_type == "text/javascript; charset=utf-8"
    assert stylesheet_type == "text/css; charset=utf-8"
    assert b"Matylda Praxis" in index
    assert b'fetch(path' in script
    assert b"/hypotheses" in script
    assert b".workflow-layout" in stylesheet
    assert load_static_asset("/not-an-asset") is None


def test_reference_api_runs_the_complete_waiting_protocol(tmp_path):
    api = api_for(tmp_path / "api.db")
    status, created = api.dispatch("POST", "/hypotheses", {"title": "HTTP E2E"})
    assert status == 201
    artifact_id = created["hypothesis"]["id"]

    for state in ("incubator", "exploration"):
        status, _ = api.dispatch(
            "POST", f"/hypotheses/{artifact_id}/advance", {"state": state},
        )
        assert status == 200
    status, _ = api.dispatch("POST", f"/hypotheses/{artifact_id}/advance", {
        "state": "working",
        "artifact": ARTIFACT,
    })
    assert status == 200
    assert api.dispatch("POST", f"/hypotheses/{artifact_id}/preflight", {})[1]["preflight"]["issues"] == []
    status, benchmark = api.dispatch(
        "POST", f"/hypotheses/{artifact_id}/benchmark", BENCHMARK,
    )
    assert status == 200
    status, review = api.dispatch("POST", f"/hypotheses/{artifact_id}/review", {
        **REVIEW,
        "benchmark_id": benchmark["benchmark"]["benchmark_id"],
    })
    assert status == 200

    status, denied = api.dispatch("POST", f"/hypotheses/{artifact_id}/decision", {
        "decision": "WAIT",
        "rationale": "Wait for replication.",
        "operator_id": "api-operator",
        "reentry_condition": "Replication available.",
        "review_date": "2026-10-01",
    })
    assert status == 400
    assert "confirmed_by_human" in denied["error"]

    status, decision = api.dispatch("POST", f"/hypotheses/{artifact_id}/decision", {
        "decision": "WAIT",
        "rationale": "Wait for replication.",
        "operator_id": "api-operator",
        "confirmed_by_human": True,
        "reentry_condition": "Replication available.",
        "review_date": "2026-10-01",
    })
    assert status == 200
    assert decision["decision"]["review_id"] == review["review"]["review_id"]
    final = api.dispatch("GET", f"/hypotheses/{artifact_id}")[1]["hypothesis"]
    assert final["decision_memos"][-1]["decision"] == "WAIT"


def test_reference_api_rejects_unknown_routes_and_malicious_review(tmp_path):
    api = api_for(tmp_path / "api.db")
    assert api.dispatch("GET", "/unknown")[0] == 404
    artifact_id = api.dispatch(
        "POST", "/hypotheses", {"title": "Injection"},
    )[1]["hypothesis"]["id"]

    status, payload = api.dispatch("POST", f"/hypotheses/{artifact_id}/review", {
        **REVIEW,
        "benchmark_id": "bench-fake",
        "decision": "PUBLISH",
    })

    assert status == 400
    assert payload["ok"] is False


def test_cli_persists_records_between_independent_invocations(tmp_path, capsys):
    database = str(tmp_path / "cli.db")
    assert main(["--db", database, "create", "CLI seed"]) == 0
    created = json.loads(capsys.readouterr().out)

    assert main(["--db", database, "show", created["id"]]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["title"] == "CLI seed"

    assert main(["--db", database, "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [item["id"] for item in listed] == [created["id"]]


def test_cli_reports_protocol_errors_without_traceback(tmp_path, capsys):
    database = str(tmp_path / "cli.db")
    exit_code = main(["--db", database, "show", "hyp-missing"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "Unknown artifact" in json.loads(captured.err)["error"]


def test_cli_reports_a_concurrent_write_without_traceback(tmp_path, capsys, monkeypatch):
    database = str(tmp_path / "cli.db")
    assert main(["--db", database, "create", "CLI seed"]) == 0
    created = json.loads(capsys.readouterr().out)

    fresh = SQLiteArtifactRepository.get

    def stale_read(self, artifact_id):
        # A second writer committed between this read and its write.
        return replace(fresh(self, artifact_id), revision=-1)

    monkeypatch.setattr(SQLiteArtifactRepository, "get", stale_read)
    exit_code = main(["--db", database, "advance", created["id"], "incubator"])
    captured = capsys.readouterr()

    assert exit_code == 3
    assert captured.out == ""
    assert "changed before this write could commit" in json.loads(captured.err)["error"]


def test_cli_lab_import_is_dry_run_until_apply(tmp_path, capsys):
    source = tmp_path / "legacy.json"
    source.write_text(json.dumps({
        "schema_version": 2,
        "records": [{
            "id": "hyp-cli-import",
            "title": "CLI imported seed",
            "state": "seed",
            "created_at": "2026-08-01T12:00:00+00:00",
            "updated_at": "2026-08-01T12:00:00+00:00",
            "parent_id": None,
            "assumptions": [],
            "evidence_for": [],
            "evidence_against": [],
        }],
        "events": [],
    }), encoding="utf-8")
    database = str(tmp_path / "import.db")

    assert main([
        "--db", database, "import-lab", str(source), "--id", "hyp-cli-import",
    ]) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["ready"] == ["hyp-cli-import"]
    assert dry_run["imported"] == []

    assert main([
        "--db", database, "import-lab", str(source),
        "--id", "hyp-cli-import", "--apply",
    ]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["imported"] == ["hyp-cli-import"]

    assert main(["--db", database, "show", "hyp-cli-import"]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["title"] == "CLI imported seed"


def test_serve_defaults_to_loopback_only():
    args = build_parser().parse_args(["serve"])
    assert args.host == "127.0.0.1"
    assert args.port == 8787


def test_cli_server_stops_cleanly_on_keyboard_interrupt(tmp_path, monkeypatch):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("matylda_praxis.cli.serve", interrupted)

    assert main(["--db", str(tmp_path / "server.db"), "serve"]) == 0
