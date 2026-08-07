from __future__ import annotations

import os

from matylda_praxis.config import load_local_env


def test_local_env_loads_only_known_provider_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("UNRELATED_SECRET", raising=False)
    path = tmp_path / ".env.local"
    path.write_text(
        "OPENAI_API_KEY='test-key'\n"
        "OPENAI_MODEL=gpt-test\n"
        "UNRELATED_SECRET=ignored\n",
        encoding="utf-8",
    )

    assert load_local_env(path) == ("OPENAI_API_KEY", "OPENAI_MODEL")
    assert os.environ["OPENAI_API_KEY"] == "test-key"
    assert os.environ["OPENAI_MODEL"] == "gpt-test"
    assert "UNRELATED_SECRET" not in os.environ


def test_local_env_never_overrides_process_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "process-model")
    path = tmp_path / ".env.local"
    path.write_text("OPENAI_MODEL=file-model\n", encoding="utf-8")

    assert load_local_env(path) == ()
    assert os.environ["OPENAI_MODEL"] == "process-model"
