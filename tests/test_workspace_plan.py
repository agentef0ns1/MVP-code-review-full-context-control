"""Tests for workspace plan + bounded read."""
from __future__ import annotations

from pathlib import Path

import pytest

from mvp_memory.config import Settings
from mvp_memory.core.store import MemoryStore


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    s = Settings.from_args(data_dir=tmp_path / "data")
    return MemoryStore(s)


def test_workspace_plan_and_read(tmp_path: Path) -> None:
    store = MemoryStore(Settings.from_args(data_dir=tmp_path / "data"))
    code = tmp_path / "mirror"
    code.mkdir()
    (code / "init.js").write_text("var t = localStorage.getItem('access_token');\n", encoding="utf-8")
    (code / "big.js").write_text("x" * 200_000, encoding="utf-8")

    store.create_project("p1", workspace_path=str(code))
    plan = store.workspace_plan("p1", reset=True)
    assert plan["unit_count"] == 2
    assert plan["next_unit"]["unit_id"] == "chunk-0001"
    assert plan["next_unit"]["rel_paths"] == ["init.js"]
    assert plan["next_unit"]["read_rel_path"] == "init.js"

    read = store.workspace_read("p1", "init.js", line_limit=50)
    assert "access_token" in read["content"]
    prefixed = store.workspace_read("p1", "chunk-0001/init.js", line_limit=50)
    assert prefixed["rel_path"] == "init.js"
    assert prefixed["corrected_from"] == "chunk-0001/init.js"
    assert "access_token" in prefixed["content"]

    nxt = store.workspace_complete_unit("p1", "chunk-0001")
    assert nxt["unit"]["rel_paths"] == ["big.js"]
    assert nxt["unit"]["strategy"] == "rg_windows"


def test_path_traversal_blocked(tmp_path: Path) -> None:
    store = MemoryStore(Settings.from_args(data_dir=tmp_path / "data2"))
    code = tmp_path / "mirror"
    code.mkdir()
    store.create_project("p2", workspace_path=str(code))
    from mvp_memory.core.errors import MemoryError

    with pytest.raises(MemoryError):
        store.workspace_read("p2", "../etc/passwd")