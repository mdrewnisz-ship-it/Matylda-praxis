from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from matylda_praxis.adapters.sqlite import SQLITE_SCHEMA_VERSION, SQLiteArtifactRepository


ROOT = Path(__file__).parents[2]


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    return env


def test_committed_record_survives_abrupt_process_exit(tmp_path):
    database = tmp_path / "abrupt.db"
    script = """
import os, sys
from matylda_praxis.adapters.sqlite import SQLiteArtifactRepository
from matylda_praxis.domain.models import HypothesisRecord
repo = SQLiteArtifactRepository(sys.argv[1])
repo.save(HypothesisRecord.seed('Committed before exit'), expected_revision=None)
os._exit(0)
"""
    subprocess.run(
        [sys.executable, "-c", script, str(database)],
        check=True,
        cwd=ROOT,
        env=child_env(),
    )

    recovered = SQLiteArtifactRepository(database)

    assert [record.title for record in recovered.list()] == ["Committed before exit"]
    assert recovered.integrity_check() == ("ok",)


def test_uncommitted_write_is_rolled_back_after_abrupt_exit(tmp_path):
    database = tmp_path / "rollback.db"
    script = """
import os, sqlite3, sys
from matylda_praxis.adapters.sqlite import SQLiteArtifactRepository
SQLiteArtifactRepository(sys.argv[1])
connection = sqlite3.connect(sys.argv[1])
connection.execute('BEGIN IMMEDIATE')
connection.execute(
    'INSERT INTO artifacts (id, revision, updated_at, payload) VALUES (?, ?, ?, ?)',
    ('partial', 0, 'now', '{}'),
)
os._exit(0)
"""
    subprocess.run(
        [sys.executable, "-c", script, str(database)],
        check=True,
        cwd=ROOT,
        env=child_env(),
    )

    recovered = SQLiteArtifactRepository(database)

    assert recovered.list() == ()
    assert recovered.integrity_check() == ("ok",)


def test_future_sqlite_schema_is_rejected_without_mutation(tmp_path):
    database = tmp_path / "future.db"
    with sqlite3.connect(database) as connection:
        connection.execute(f"PRAGMA user_version = {SQLITE_SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError, match="newer than supported"):
        SQLiteArtifactRepository(database)
