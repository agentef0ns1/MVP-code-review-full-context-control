"""Walk an audit plan without putting file contents in the model context."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mvp_memory import SCHEMA_VERSION
from mvp_memory.core.errors import MemoryError

_MAX_RESPONSE_CHARS = 2_000


def run_audit(
    store: Any,
    *,
    target_directory: str | None = None,
    project_id: str | None = None,
    profile_id: str = "security-full",
    reset: bool = False,
    actor: str = "agent",
    session_id: str | None = None,
) -> dict[str, Any]:
    """Process every pending unit, skip failures, and write the executive summary.

    A later call with the same project_id resumes from SQLite and does not
    reopen units already marked done or skipped.
    """
    if target_directory:
        started = store.audit_start(
            target_directory,
            profile_id=profile_id,
            reset=reset,
            actor=actor,
            session_id=session_id,
        )
        project_id = started["project_id"]
    if not project_id:
        raise MemoryError("invalid", "target_directory or project_id is required")

    out = _output_dir(store, project_id)
    if reset and target_directory:
        _reset_run_artifacts(out)

    units_done = 0
    units_skipped = 0
    while True:
        nxt = store.workspace_next_unit(project_id, actor)
        unit = nxt.get("unit")
        if not unit or nxt.get("done"):
            break
        unit_id = str(unit.get("unit_id") or "")
        rel = str(unit.get("read_rel_path") or "")
        if not rel:
            rels = unit.get("rel_paths") or []
            rel = str(rels[0]) if rels else ""
        try:
            _visit_unit(store, project_id, unit, rel, actor)
            store.workspace_complete_unit(
                project_id, unit_id, skip=False, actor=actor, session_id=session_id
            )
            _append_unit_index(out, unit_id, rel, "done")
            units_done += 1
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            _append_incident(out, unit_id or "?", rel or "?", message)
            try:
                store.workspace_complete_unit(
                    project_id,
                    unit_id,
                    skip=True,
                    actor=actor,
                    session_id=session_id,
                )
            except Exception as skip_exc:
                _append_incident(
                    out,
                    unit_id or "?",
                    rel or "?",
                    f"no se pudo saltar la unidad: {skip_exc}",
                )
                break
            _append_unit_index(out, unit_id, rel, "skipped")
            units_skipped += 1

    fin = store.audit_finalize(project_id, actor)
    incidentes = out / "INCIDENTES.md"
    store.update_summary(
        project_id,
        summary=(
            f"Auditoría terminada. Unidades de este pase: {units_done}. "
            f"Saltadas: {units_skipped}."
        ),
        checkpoint="audit:run:done",
        actor=actor,
        session_id=session_id,
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "done": True,
        "project_id": project_id,
        "units_done": units_done,
        "units_skipped": units_skipped,
        "incident_count": units_skipped,
        "resumen_path": fin.get("resumen_path") or str(out / "RESUMEN-EJECUTIVO.md"),
        "incidentes_path": str(incidentes) if incidentes.is_file() else "",
    }
    return _cap_result(result)


def _output_dir(store: Any, project_id: str) -> Path:
    with store.db.transaction() as conn:
        _root, out, _cfg = store.audit_session._output_root(conn, project_id)
    return out


def _reset_run_artifacts(out: Path) -> None:
    for name in ("INCIDENTES.md",):
        path = out / name
        if path.is_file():
            path.unlink()
    index = out / "scans" / "INDICE-UNIDADES.md"
    if index.is_file():
        index.unlink()


def _visit_unit(store: Any, project_id: str, unit: dict, rel: str, actor: str) -> None:
    if not rel:
        raise MemoryError("invalid", "unidad sin read_rel_path")
    if unit.get("strategy") == "rg_windows":
        store.workspace_read(
            project_id,
            rel,
            byte_limit=256,
            max_bytes=256,
            line_limit=1,
            actor=actor,
        )
        return
    store.workspace_read(project_id, rel, line_limit=40, actor=actor)


def _append_incident(out: Path, unit_id: str, rel_path: str, error: str) -> None:
    path = out / "INCIDENTES.md"
    if not path.is_file():
        path.write_text(
            "# Incidentes\n\nUnidades saltadas. Revisar después.\n\n",
            encoding="utf-8",
        )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"## {unit_id}\n\n- rel_path: `{rel_path}`\n- error: {error}\n\n"
        )


def _append_unit_index(out: Path, unit_id: str, rel_path: str, status: str) -> None:
    path = out / "scans" / "INDICE-UNIDADES.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text("# Índice de unidades\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"- {unit_id} `{rel_path}` {status}\n")


def _cap_result(result: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(result, ensure_ascii=False)
    if len(raw) <= _MAX_RESPONSE_CHARS:
        return result
    return {
        "schema_version": result.get("schema_version", SCHEMA_VERSION),
        "done": True,
        "project_id": result.get("project_id", ""),
        "units_done": result.get("units_done", 0),
        "units_skipped": result.get("units_skipped", 0),
        "incident_count": result.get("incident_count", 0),
        "resumen_path": result.get("resumen_path", ""),
        "incidentes_path": "",
    }
