from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mvp_memory.config import Settings
from mvp_memory.core.errors import MemoryError
from mvp_memory.core.workspace_plan import WorkspacePlanService
from mvp_memory.core.static_analysis import run_static_tools
from mvp_memory.audit_findings import write_scan_index, record_finding, finalize_audit


class AuditSessionService:
    def __init__(self, settings: Settings, workspace: WorkspacePlanService) -> None:
        self.settings = settings
        self.workspace = workspace

    def _output_root(self, conn, project_id: str) -> tuple[Path, Path, dict]:
        row = conn.execute(
            "SELECT * FROM audit_sessions WHERE project_id=?", (project_id,)
        ).fetchone()
        if not row:
            raise MemoryError(
                "not_found",
                "No hay sesión de auditoría; usa memory_audit_start primero",
            )
        root = self.workspace._project_root(conn, project_id)
        cfg = json.loads(row["config_json"] or "{}")
        cfg["profile_id"] = row["profile_id"]
        out_rel = row["output_rel_dir"] or ".mvp-audit"
        out = (root / out_rel).resolve()
        if not str(out).startswith(str(root.resolve())):
            raise MemoryError("invalid", "output_dir outside workspace")
        return root, out, cfg

    def scaffold_output(self, out: Path, profile: dict[str, Any]) -> None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "findings").mkdir(exist_ok=True)
        (out / "poc").mkdir(exist_ok=True)
        (out / "scans").mkdir(exist_ok=True)
        (out / "unidades").mkdir(exist_ok=True)
        (out / "static").mkdir(exist_ok=True)
        idx = out / (profile.get("findings") or {}).get("index", "indice.md")
        if not idx.is_file():
            idx.write_text(
                "# Índice de hallazgos\n\n"
                "| ID | Severidad | Resumen | Finding | PoC | Estado |\n"
                "|----|-----------|---------|---------|-----|--------|\n",
                encoding="utf-8",
            )
        (out / "session.json").write_text(
            json.dumps(
                {"profile_id": profile["id"], "output_dir": str(out)},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def run_profile_scans(
        self,
        conn,
        project_id: str,
        profile: dict[str, Any],
        scans_dir: Path,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for s in profile.get("searches") or []:
            pattern = s["pattern"]
            max_count = int(s.get("max_count", 15))
            safe = s["id"].replace("/", "_")
            artifact = scans_dir / f"{safe}.txt"
            try:
                preview = self.workspace.scan_pattern(
                    conn,
                    project_id,
                    pattern,
                    rel_path=None,
                    max_count=max_count,
                )
            except MemoryError as e:
                artifact.write_text(f"# scan skipped: {e}\n", encoding="utf-8")
                results.append(
                    {"search_id": s["id"], "artifact": str(artifact), "error": str(e)}
                )
                continue
            src = Path(preview["artifact_path"])
            if src.is_file():
                artifact.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            results.append(
                {
                    "search_id": s["id"],
                    "label": s.get("label", ""),
                    "artifact": str(artifact),
                    "line_count": preview.get("line_count", 0),
                }
            )
        return results
