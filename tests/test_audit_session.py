"""Audit start flow with profiles."""
from __future__ import annotations

from pathlib import Path

from mvp_memory.config import Settings
from mvp_memory.core.store import MemoryStore


def test_audit_start_baseline(tmp_path: Path) -> None:
    code = tmp_path / "app"
    code.mkdir()
    (code / "init.js").write_text("localStorage.getItem('x');\n", encoding="utf-8")

    store = MemoryStore(Settings.from_args(data_dir=tmp_path / "data"))
    r = store.audit_start(str(code), profile_id="security-baseline", reset=True)

    assert r["project_id"]
    assert (code / ".mvp-audit" / "indice.md").is_file()
    assert (code / ".mvp-audit" / "scans").is_dir()
    assert "session_prompt" in r and len(r["session_prompt"]) > 100
    assert r["next_unit"]

    st = store.audit_status(r["project_id"])
    assert ".mvp-audit" in st["output_dir"]

    step = store.audit_next_step(r["project_id"])
    assert step["unit"]["unit_id"] == "chunk-0001"
    assert step["unit"]["read_rel_path"] == "init.js"
    assert "profile_searches" not in step
    assert "memory_workspace_read" in step["do_now"]

    pr = store.list_audit_profiles()
    assert any(p["id"] == "js-console-api" for p in pr["profiles"])

    prompt = store.get_audit_prompt("js-console-api", str(code))
    assert "js-console-api" in prompt["prompt_markdown"]
