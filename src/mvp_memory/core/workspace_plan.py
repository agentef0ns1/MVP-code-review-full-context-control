from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mvp_memory.config import Settings, new_uuid
from mvp_memory.core.db import row_to_dict
from mvp_memory.core.errors import MemoryError

SKIP_DIR_NAMES = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "coverage",
    ".pytest_cache",
    "security-audit",
    "security-audit-frontend",
    ".mvp-audit",
}

SCANNABLE_EXTENSIONS = {
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".go",
    ".java",
    ".kt",
    ".rb",
    ".php",
    ".vue",
    ".svelte",
    ".sql",
    ".sh",
    ".xml",
    ".svg",
    ".map",
}

LARGE = 500_000
JS_CSS_RG = 150_000
READ_MAX_BYTES_DEFAULT = 48_000
RG_MAX_COLUMNS = 220

PRIORITY_NAMES = (
    "init.js",
    "appStatusInit.js",
    "runtime",
    "polyfills",
    "scripts.",
    "manifest.json",
    "page.html",
)


@dataclass
class FileEntry:
    rel: str
    bytes: int
    ext: str


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_UNIT_DIR_PREFIX = re.compile(r"^chunk-\d+/")


def strip_mistaken_unit_prefix(root: Path, rel_path: str) -> tuple[str, str | None]:
    """A local model joins unit_id and the file: chunk-0001/function.json."""
    rel = rel_path.replace("\\", "/").lstrip("/")
    if resolve_under_root(root, rel).is_file():
        return rel, None
    stripped = rel
    while _UNIT_DIR_PREFIX.match(stripped):
        stripped = _UNIT_DIR_PREFIX.sub("", stripped, count=1)
        if stripped and resolve_under_root(root, stripped).is_file():
            return stripped, rel
    return rel, None


def annotate_pending_unit(project_id: str, unit: dict[str, Any]) -> dict[str, Any]:
    rels = unit.get("rel_paths") or []
    rel = rels[0] if rels else ""
    if unit.get("strategy") == "rg_windows":
        read_with = (
            f'memory_workspace_scan_patterns(project_id="{project_id}", rel_path="{rel}")'
        )
    else:
        read_with = (
            f'memory_workspace_read(project_id="{project_id}", rel_path="{rel}")'
        )
    return {
        **unit,
        "read_rel_path": rel,
        "read_with": read_with,
        "complete_with": (
            f'memory_workspace_complete_unit(project_id="{project_id}", unit_id="{unit.get("unit_id", "")}")'
        ),
        "note": (
            "unit_id no es una carpeta. Pasa read_rel_path tal cual, sin anteponer chunk-NNNN/. "
            "No uses read_files, ls ni find para localizar la unidad."
        ),
    }


def _with_path_correction(payload: dict[str, Any], corrected_from: str | None) -> dict[str, Any]:
    if not corrected_from:
        return payload
    payload["corrected_from"] = corrected_from
    payload["note"] = (
        "El unit_id no forma parte de la ruta. Siguiente paso: "
        "memory_workspace_complete_unit con el unit_id, luego memory_workspace_next_unit."
    )
    return payload


def resolve_under_root(root: Path, rel_path: str) -> Path:
    root = root.resolve()
    rel = rel_path.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise MemoryError("invalid", "path traversal not allowed")
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as e:
        raise MemoryError("invalid", "path outside workspace") from e
    return target


def collect_files(target: Path) -> list[FileEntry]:
    target = target.resolve()
    entries: list[FileEntry] = []
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(target).parts
        if any(part in SKIP_DIR_NAMES for part in rel_parts):
            continue
        ext = path.suffix.lower()
        if ext not in SCANNABLE_EXTENSIONS and path.name not in (
            ".env",
            ".env.local",
            ".env.production",
        ):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        entries.append(
            FileEntry(
                rel=path.relative_to(target).as_posix(),
                bytes=size,
                ext=ext or path.name,
            )
        )
    return entries


def _sort_key(e: FileEntry) -> tuple[int, int, str]:
    base = Path(e.rel).name.lower()
    for i, frag in enumerate(PRIORITY_NAMES):
        f = frag.lower()
        if f.endswith(".js") or f.endswith(".json") or f.endswith(".html"):
            if base == f:
                return (0, i, e.rel)
        elif f.endswith("."):
            if base.startswith(f):
                return (0, i, e.rel)
        elif base == f:
            return (0, i, e.rel)
    if e.ext == ".svg":
        return (2, e.bytes, e.rel)
    return (1, e.bytes, e.rel)


def file_strategy(entry: FileEntry) -> str:
    if entry.bytes >= LARGE:
        return "rg_windows"
    if entry.ext in {".js", ".mjs", ".cjs", ".css", ".scss"} and entry.bytes >= JS_CSS_RG:
        return "rg_windows"
    return "read_ok"


def build_units(entries: list[FileEntry]) -> list[dict[str, Any]]:
    ordered = sorted(entries, key=_sort_key)
    units: list[dict[str, Any]] = []
    for i, e in enumerate(ordered, start=1):
        uid = f"chunk-{i:04d}"
        units.append(
            {
                "unit_id": uid,
                "sequence": i,
                "rel_paths": [e.rel],
                "total_bytes": e.bytes,
                "strategy": file_strategy(e),
                "checkpoint_key": f"audit:{uid}:done",
            }
        )
    return units


class WorkspacePlanService:
    def __init__(self, settings: Settings, db) -> None:
        self.settings = settings
        self.db = db

    def _project_root(self, conn, project_id: str) -> Path:
        row = conn.execute(
            "SELECT workspace_path FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        if not row or not row["workspace_path"]:
            raise MemoryError(
                "invalid", "project has no workspace_path; set on create_project"
            )
        root = Path(row["workspace_path"]).expanduser().resolve()
        if not root.is_dir():
            raise MemoryError("not_found", f"workspace_path not found: {root}")
        return root

    def plan(
        self,
        conn,
        project_id: str,
        *,
        profile: str = "security_code",
        reset: bool = False,
    ) -> dict:
        root = self._project_root(conn, project_id)
        existing = conn.execute(
            "SELECT unit_count FROM workspace_plans WHERE project_id=?", (project_id,)
        ).fetchone()
        if existing and not reset:
            nxt = self.next_unit(conn, project_id)
            return {
                "project_id": project_id,
                "workspace_path": str(root),
                "profile": profile,
                "file_count": None,
                "unit_count": int(existing["unit_count"]),
                "next_unit": nxt.get("unit"),
                "approx_tokens_next": (nxt.get("unit") or {}).get("approx_tokens", 0),
                "reused_existing_plan": True,
            }

        if reset or existing:
            conn.execute("DELETE FROM workspace_units WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM workspace_plans WHERE project_id=?", (project_id,))

        entries = collect_files(root)
        units = build_units(entries)
        now = _now()
        conn.execute(
            """
            INSERT INTO workspace_plans (project_id, profile, created_at, updated_at, unit_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                profile=excluded.profile,
                updated_at=excluded.updated_at,
                unit_count=excluded.unit_count
            """,
            (project_id, profile, now, now, len(units)),
        )
        for u in units:
            conn.execute(
                """
                INSERT INTO workspace_units (
                    id, project_id, unit_id, sequence, rel_paths_json,
                    total_bytes, strategy, status, checkpoint_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    new_uuid(),
                    project_id,
                    u["unit_id"],
                    u["sequence"],
                    json.dumps(u["rel_paths"]),
                    u["total_bytes"],
                    u["strategy"],
                    u["checkpoint_key"],
                ),
            )
        nxt = self.next_unit(conn, project_id)
        return {
            "project_id": project_id,
            "workspace_path": str(root),
            "profile": profile,
            "file_count": len(entries),
            "unit_count": len(units),
            "next_unit": nxt.get("unit"),
            "approx_tokens_next": (nxt.get("unit") or {}).get("approx_tokens", 0),
        }

    def next_unit(self, conn, project_id: str) -> dict:
        row = conn.execute(
            """
            SELECT * FROM workspace_units
            WHERE project_id=? AND status='pending'
            ORDER BY sequence ASC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        if not row:
            return {
                "project_id": project_id,
                "unit": None,
                "done": True,
                "next_tool": "memory_audit_finalize",
                "note": (
                    "No quedan unidades. No busques carpetas chunk-*. "
                    "Llama memory_audit_finalize y termina."
                ),
            }
        u = row_to_dict(row) or {}
        rel_paths = json.loads(u.get("rel_paths_json") or "[]")
        unit = annotate_pending_unit(
            project_id,
            {
                "unit_id": u["unit_id"],
                "rel_paths": rel_paths,
                "total_bytes": u["total_bytes"],
                "strategy": u["strategy"],
                "checkpoint_key": u["checkpoint_key"],
                "approx_tokens": max(1, int(u["total_bytes"]) // 4),
                "read_budget_bytes": READ_MAX_BYTES_DEFAULT,
            },
        )
        return {"project_id": project_id, "unit": unit, "done": False}

    def complete_unit(
        self,
        conn,
        project_id: str,
        unit_id: str,
        *,
        skip: bool = False,
    ) -> dict:
        row = conn.execute(
            "SELECT * FROM workspace_units WHERE project_id=? AND unit_id=?",
            (project_id, unit_id),
        ).fetchone()
        if not row:
            raise MemoryError("not_found", f"unit {unit_id} not found")
        status = "skipped" if skip else "done"
        conn.execute(
            "UPDATE workspace_units SET status=? WHERE project_id=? AND unit_id=?",
            (status, project_id, unit_id),
        )
        return self.next_unit(conn, project_id)

    def read_bounded(
        self,
        conn,
        project_id: str,
        rel_path: str,
        *,
        line_offset: int = 1,
        line_limit: int = 120,
        byte_offset: int = 0,
        byte_limit: int = 0,
        max_bytes: int = READ_MAX_BYTES_DEFAULT,
    ) -> dict:
        root = self._project_root(conn, project_id)
        rel_path, corrected_from = strip_mistaken_unit_prefix(root, rel_path)
        path = resolve_under_root(root, rel_path)
        if not path.is_file():
            raise MemoryError(
                "not_found",
                f"file not found: {rel_path}. unit_id no es una carpeta. "
                "Usa read_rel_path de memory_workspace_next_unit tal cual, sin anteponer chunk-NNNN/. "
                "No ejecutes ls ni find.",
            )
        size = path.stat().st_size
        cap = min(max_bytes, READ_MAX_BYTES_DEFAULT)
        use_bytes = byte_limit > 0 or (
            size > JS_CSS_RG
            and path.suffix.lower() in {".js", ".mjs", ".cjs", ".css", ".scss"}
        )
        if use_bytes:
            start = max(0, byte_offset)
            limit = byte_limit if byte_limit > 0 else cap
            limit = min(limit, cap)
            with path.open("rb") as f:
                f.seek(start)
                chunk = f.read(limit)
            text = chunk.decode("utf-8", errors="replace")
            return _with_path_correction(
                {
                    "rel_path": rel_path,
                    "mode": "bytes",
                    "byte_offset": start,
                    "byte_limit": limit,
                    "file_bytes": size,
                    "content": text,
                    "truncated": start + limit < size,
                    "approx_tokens": len(text) // 4,
                },
                corrected_from,
            )
        lines: list[str] = []
        total = 0
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                if i < line_offset:
                    continue
                if len(lines) >= line_limit:
                    break
                b = len(line.encode("utf-8"))
                if total + b > cap:
                    break
                lines.append(line)
                total += b
        content = "".join(lines)
        return _with_path_correction(
            {
                "rel_path": rel_path,
                "mode": "lines",
                "line_offset": line_offset,
                "line_limit": line_limit,
                "file_bytes": size,
                "content": content,
                "truncated": len(lines) >= line_limit or total >= cap,
                "approx_tokens": len(content) // 4,
            },
            corrected_from,
        )

    def scan_pattern(
        self,
        conn,
        project_id: str,
        pattern: str,
        *,
        rel_path: str | None = None,
        max_count: int = 15,
    ) -> dict:
        root = self._project_root(conn, project_id)
        artifacts = self.settings.data_dir / "artifacts" / project_id
        artifacts.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", pattern)[:48]
        out_path = artifacts / f"rg_{safe_name}.txt"
        target = str(resolve_under_root(root, rel_path)) if rel_path else str(root)
        cmd = [
            "rg",
            "-n",
            "--no-heading",
            "--color=never",
            f"--max-count={max_count}",
            f"--max-columns={RG_MAX_COLUMNS}",
            "-S",
            pattern,
            target,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            body = proc.stdout or ""
        except FileNotFoundError:
            raise MemoryError("unavailable", "ripgrep (rg) not installed") from None
        except subprocess.TimeoutExpired:
            body = "# rg timeout\n"
        lines = [
            ln
            for ln in body.splitlines()
            if "/security-audit" not in ln.replace("\\", "/")
        ]
        header = f"# pattern: {pattern}\n# target: {target}\n\n"
        out_path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
        preview = lines[:8]
        return {
            "artifact_path": str(out_path),
            "line_count": len(lines),
            "preview_lines": preview,
            "approx_tokens_preview": sum(len(x) for x in preview) // 4,
        }
