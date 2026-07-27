from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mvp_memory.config import project_id_from_workspace
from mvp_memory.core.errors import MemoryError

_PROFILES_DIR = Path(__file__).resolve().parent / "audit_profiles"


def profiles_dir() -> Path:
    return _PROFILES_DIR


def list_profiles() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for path in sorted(_PROFILES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append(
            {
                "id": data["id"],
                "title": data.get("title", data["id"]),
                "description": data.get("description", ""),
                "output_dir_default": data.get("output_dir_default", ".mvp-audit"),
            }
        )
    return out


def load_profile(profile_id: str, _stack: frozenset[str] | None = None) -> dict[str, Any]:
    stack = _stack or frozenset()
    if profile_id in stack:
        raise MemoryError("invalid", f"Circular extends in profile: {profile_id}")
    path = _PROFILES_DIR / f"{profile_id}.json"
    if not path.is_file():
        available = ", ".join(p.stem for p in _PROFILES_DIR.glob("*.json"))
        raise MemoryError(
            "not_found",
            f"Perfil '{profile_id}' no existe. Disponibles: {available}",
        )
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    extends = data.pop("extends", None)
    if not extends:
        data.setdefault("id", profile_id)
        return data

    merged: dict[str, Any] = {
        "searches": [],
        "tasks": [],
        "static_tools": [],
    }
    for ext in extends:
        base = load_profile(ext, stack | {profile_id})
        merged = _merge_profile_dicts(merged, base)
    merged = _merge_profile_dicts(merged, data)
    merged["id"] = data.get("id", profile_id)
    if "title" in data:
        merged["title"] = data["title"]
    if "description" in data:
        merged["description"] = data["description"]
    return merged


def _merge_profile_dicts(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for key in ("output_dir_default", "findings", "poc", "agent_instructions"):
        if key in b:
            out[key] = b[key]

    searches: dict[str, dict] = {s["id"]: s for s in out.get("searches") or [] if "id" in s}
    for s in b.get("searches") or []:
        if "id" in s:
            searches[s["id"]] = s
    out["searches"] = list(searches.values())

    tasks: dict[str, dict] = {t["id"]: t for t in out.get("tasks") or [] if "id" in t}
    for t in b.get("tasks") or []:
        if "id" in t:
            tasks[t["id"]] = t
    out["tasks"] = list(tasks.values())

    static: dict[str, dict] = {t["id"]: t for t in out.get("static_tools") or [] if "id" in t}
    for t in b.get("static_tools") or []:
        if "id" in t:
            static[t["id"]] = t
    out["static_tools"] = list(static.values())

    if b.get("agent_instructions") and out.get("agent_instructions"):
        if b["agent_instructions"] not in out["agent_instructions"]:
            out["agent_instructions"] = out["agent_instructions"] + "\n" + b["agent_instructions"]
    return out


def load_profile_flat(profile_id: str) -> dict[str, Any]:
    """Alias público."""
    return load_profile(profile_id)


def render_audit_prompt(profile: dict[str, Any], ctx: dict[str, str]) -> str:
    """Plantilla de sesión para el agente (markdown)."""
    pid = ctx["project_id"]
    target = ctx["workspace_path"]
    out = ctx["output_dir"]
    findings = ctx.get("findings_dir", f"{out}/findings")
    poc = ctx.get("poc_dir", f"{out}/poc")
    scans = ctx.get("scans_dir", f"{out}/scans")

    searches = profile.get("searches") or []
    tasks = profile.get("tasks") or []
    instructions = profile.get("agent_instructions", "")
    for k, v in ctx.items():
        instructions = instructions.replace(f"{{{{{k}}}}}", v)

    search_lines = "\n".join(
        f"- **{s['id']}** ({s.get('label', '')}): `{s['pattern']}`"
        for s in searches
    )
    task_lines = "\n".join(
        f"- **{t['id']}** {t['title']} → `{out}/{t['deliverable']}`"
        + (" (PoC obligatorio)" if t.get("require_poc") else "")
        for t in tasks
    )
    poc_note = (profile.get("poc") or {}).get("note", "")

    return f"""# Sesión de auditoría — {profile.get("title", profile["id"])}

## Configuración (automática)
- **project_id:** `{pid}`
- **Código analizado:** `{target}`
- **Informes y findings:** `{out}`
- **Escaneos rg:** `{scans}`
- **Findings:** `{findings}`
- **PoC:** `{poc}` — {poc_note}

## Perfil `{profile["id"]}`
{profile.get("description", "")}

## Búsquedas configuradas
{search_lines or "(ninguna)"}

## Tareas (pendientes MCP)
{task_lines or "(ninguna)"}

## Instrucciones
{instructions}

## Flujo MCP (orden)
1. `memory_get_checkpoint(project_id="{pid}", auto_create=true)` — ≤3 bullets.
2. `memory_audit_status(project_id="{pid}")` — progreso y rutas.
3. Por cada hallazgo confirmado: **`memory_audit_record_finding(...)`** (escribe FIND-* en disco).
4. Bucle: `memory_audit_next_step` → analizar → **record_finding** → `memory_audit_complete_step`.
5. Cierre: **`memory_audit_finalize(project_id="{pid}")`** — genera RESUMEN-EJECUTIVO.md; no declares "COMPLETE" sin esto.
6. No volcar bundles al chat; solo `memory_workspace_read` / `{scans}`.

## Cobertura inyecciones
Si el perfil incluye `security-injection` o `security-full`: revisar scans `xss-dom`, `xss-url`, `sqli-sql`, `ssrf-fetch`, `param-validation`, etc.
Semgrep (perfil `security-static-first`) añade reglas adicionales en `static/semgrep.json`.

## PoC
required={json.dumps((profile.get("poc") or {}).get("required", False))}
"""


def list_prompt_catalog() -> list[dict[str, str]]:
    """Catálogo de prompts consultables (paralelo a perfiles)."""
    items = []
    for p in list_profiles():
        items.append(
            {
                "prompt_id": f"audit/{p['id']}",
                "profile_id": p["id"],
                "title": p["title"],
                "tool": "memory_get_audit_prompt",
                "arg": p["id"],
            }
        )
    items.append(
        {
            "prompt_id": "guide/cline",
            "profile_id": "",
            "title": "Guía Cline / Continue / Codex",
            "tool": "memory_get_agent_guide",
            "arg": "any",
        }
    )
    return items


def slug_from_path(target: Path) -> str:
    return project_id_from_workspace(str(target.resolve()))
