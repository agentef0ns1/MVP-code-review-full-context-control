"""Registro de prompts MCP nativos (prompts/list, prompts/get)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from mvp_memory.agent_guide import load_agent_guide
from mvp_memory.audit_profiles_loader import (
    list_profiles,
    load_profile,
    render_audit_prompt,
    slug_from_path,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def _prompt_body_for_profile(profile_id: str, target_directory: str) -> str:
    profile = load_profile(profile_id)
    target = target_directory.strip() or "<TARGET_DIRECTORY>"
    if target != "<TARGET_DIRECTORY>":
        root = Path(target).expanduser().resolve()
        pid = slug_from_path(root)
        out_rel = profile.get("output_dir_default", ".mvp-audit")
        out = root / out_rel
        ctx = {
            "project_id": pid,
            "workspace_path": str(root),
            "output_dir": str(out),
            "findings_dir": str(out / "findings"),
            "poc_dir": str(out / "poc"),
            "scans_dir": str(out / "scans"),
        }
    else:
        ctx = {
            "project_id": "<auto via memory_audit_start>",
            "workspace_path": "<TARGET_DIRECTORY>",
            "output_dir": "<TARGET>/.mvp-audit",
            "findings_dir": "<TARGET>/.mvp-audit/findings",
            "poc_dir": "<TARGET>/.mvp-audit/poc",
            "scans_dir": "<TARGET>/.mvp-audit/scans",
        }
    body = render_audit_prompt(profile, ctx)
    from mvp_memory.audit_prompt_examples import invocation_block

    pid = ctx["project_id"]
    target_path = ctx["workspace_path"]
    return body + invocation_block(target_path, profile_id, pid)


def register_mcp_prompts(server: FastMCP) -> list[str]:
    """Registra prompts audit-* y guide-*; devuelve nombres registrados."""
    if os.environ.get("MVP_MEMORY_DISABLE_MCP_PROMPTS", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        return []

    names: list[str] = []

    for meta in list_profiles():
        pid = meta["id"]

        def _make_audit_prompt(profile_id: str, title: str, description: str):
            @server.prompt(
                name=f"audit-{profile_id}",
                title=title,
                description=description or f"Auditoría perfil {profile_id}",
            )
            def audit_profile_prompt(target_directory: str = "") -> str:
                """target_directory: ruta absoluta al código (opcional; si vacío, placeholders)."""
                return _prompt_body_for_profile(profile_id, target_directory)

            return f"audit-{profile_id}"

        names.append(_make_audit_prompt(pid, meta["title"], meta.get("description", "")))

    for client in ("cline", "continue", "codex", "any"):

        def _make_guide(client_id: str):
            @server.prompt(
                name=f"guide-{client_id}",
                title=f"Guía MCP — {client_id}",
                description=f"Invocación mvp-memory-context desde {client_id}",
            )
            def guide_prompt() -> str:
                return load_agent_guide(client_id)["guide"]

            return f"guide-{client_id}"

        names.append(_make_guide(client))

    @server.prompt(
        name="audit-quickstart",
        title="Auditoría — inicio rápido",
        description="Pasos mínimos: audit_start + record_finding + finalize",
    )
    def audit_quickstart(
        target_directory: str = "/path/to/your/repository",
        profile_id: str = "security-static-first",
    ) -> str:
        from mvp_memory.audit_prompt_examples import quickstart_prompt

        return quickstart_prompt(target_directory, profile_id)

    names.append("audit-quickstart")

    @server.prompt(
        name="audit-orchestration",
        title="Auditoría — orquestación (diagrama + pseudocódigo)",
        description="Flujo completo memory_audit_start → finalize y componentes",
    )
    def audit_orchestration_prompt() -> str:
        path = (
            Path(__file__).resolve().parent / "prompts" / "audit_orchestration.md"
        )
        return path.read_text(encoding="utf-8")

    names.append("audit-orchestration")
    return names
