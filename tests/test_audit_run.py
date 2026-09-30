"""memory_audit_run finishes the tree and can be resumed."""

from __future__ import annotations

from pathlib import Path

from mvp_memory.config import Settings
from mvp_memory.core.store import MemoryStore


def test_run_skips_missing_file_and_resume_does_not_redo(tmp_path: Path) -> None:
    code = tmp_path / "app"
    code.mkdir()
    (code / "init.js").write_text("localStorage.getItem('x');\n", encoding="utf-8")
    (code / "gone.js").write_text("var y = 1;\n", encoding="utf-8")

    store = MemoryStore(Settings.from_args(data_dir=tmp_path / "data"))
    started = store.audit_start(str(code), profile_id="security-baseline", reset=True)
    (code / "gone.js").unlink()

    first = store.audit_run(project_id=started["project_id"])
    assert first["done"] is True
    assert first["units_done"] == 1
    assert first["units_skipped"] == 1
    assert first["incident_count"] == 1
    assert Path(first["resumen_path"]).is_file()
    incidentes = Path(first["incidentes_path"])
    assert incidentes.is_file()
    text = incidentes.read_text(encoding="utf-8")
    assert "gone.js" in text
    resumen = Path(first["resumen_path"]).read_text(encoding="utf-8")
    assert "Pendiente de revisión" in resumen
    raw = __import__("json").dumps(first)
    assert len(raw) < 2_000
    assert "localStorage" not in raw

    second = store.audit_run(project_id=started["project_id"])
    assert second["done"] is True
    assert second["units_done"] == 0
    assert second["units_skipped"] == 0
    assert Path(second["resumen_path"]).is_file()
