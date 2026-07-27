from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from mvp_memory.config import Settings
from mvp_memory.core.errors import MemoryError
from mvp_memory.core.store import MemoryStore
from mvp_memory.agent_guide import load_agent_guide
from mvp_memory.mcp_prompts import register_mcp_prompts

mcp = FastMCP("mvp-memory-context")

_store: MemoryStore | None = None
_settings: Settings | None = None


def get_store() -> MemoryStore:
    global _store, _settings
    if _store is None:
        _settings = Settings.from_args()
        _store = MemoryStore(_settings)
    return _store


def _session_id() -> str | None:
    return os.environ.get("MVP_MEMORY_SESSION_ID")


def _ok(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(code: str, message: str) -> str:
    return json.dumps({"error": True, "code": code, "message": message}, ensure_ascii=False)


def _handle(fn, *args, **kwargs) -> str:
    try:
        return _ok(fn(*args, **kwargs))
    except MemoryError as e:
        return _err(e.code, str(e))
    except Exception as e:
        return _err("internal", str(e))


@mcp.tool(structured_output=False)
def memory_list_projects(status: str | None = None, limit: int = 50, offset: int = 0) -> str:
    """List memory projects with optional status filter (active, frozen, archived)."""
    return _handle(get_store().list_projects, status=status, limit=limit, offset=offset)


@mcp.tool(structured_output=False)
def memory_create_project(
    project_id: str,
    display_name: str | None = None,
    workspace_path: str | None = None,
) -> str:
    """Explicitly create a project with metadata."""
    return _handle(
        get_store().create_project,
        project_id,
        display_name,
        workspace_path,
        actor="agent",
        session_id=_session_id(),
    )


@mcp.tool(structured_output=False)
def memory_get_state(
    project_id: str,
    auto_create: bool = True,
    include_sections: list[str] | None = None,
    compact: bool = True,
) -> str:
    """Get aggregated project memory state; auto-initializes project if missing.
    Default compact=true (small JSON). Pass compact=false only for debugging."""
    return _handle(
        get_store().get_state,
        project_id,
        auto_create=auto_create,
        include_sections=include_sections,
        compact=compact,
        actor="agent",
        session_id=_session_id(),
    )


@mcp.tool(structured_output=False)
def memory_get_checkpoint(
    project_id: str,
    auto_create: bool = False,
) -> str:
    """Minimal project snapshot: summary, checkpoint, stats, slim decisions/pendings.
    Prefer this at session start instead of full get_state."""
    return _handle(
        get_store().get_checkpoint,
        project_id,
        auto_create=auto_create,
        actor="agent",
        session_id=_session_id(),
    )


@mcp.tool(structured_output=False)
def memory_append_event(
    project_id: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    scope: str = "working",
    lock_token: str | None = None,
) -> str:
    """Append a chronological milestone event."""
    return _handle(
        get_store().append_entry,
        project_id,
        "event",
        title,
        body,
        tags,
        metadata,
        scope,
        "agent",
        _session_id(),
        None,
        lock_token,
    )


@mcp.tool(structured_output=False)
def memory_add_decision(
    project_id: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    supersedes_id: str | None = None,
    lock_token: str | None = None,
) -> str:
    """Record a persistent decision."""
    return _handle(
        get_store().append_entry,
        project_id,
        "decision",
        title,
        body,
        tags,
        metadata,
        "persistent",
        "agent",
        _session_id(),
        supersedes_id,
        lock_token,
    )


@mcp.tool(structured_output=False)
def memory_add_pending(
    project_id: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    due: str | None = None,
    priority: str | None = None,
    lock_token: str | None = None,
) -> str:
    """Add an open pending task."""
    meta: dict[str, Any] = {}
    if due:
        meta["due"] = due
    if priority:
        meta["priority"] = priority
    return _handle(
        get_store().append_entry,
        project_id,
        "pending",
        title,
        body,
        tags,
        meta,
        "working",
        "agent",
        _session_id(),
        None,
        lock_token,
    )


@mcp.tool(structured_output=False)
def memory_resolve_pending(entry_id: str, resolution: str) -> str:
    """Close a pending entry with a resolution note."""
    return _handle(
        get_store().resolve_pending,
        entry_id,
        resolution,
        "agent",
        _session_id(),
    )


@mcp.tool(structured_output=False)
def memory_log_error(
    project_id: str,
    title: str,
    body: str,
    severity: str = "error",
    stack: str | None = None,
    tags: list[str] | None = None,
    lock_token: str | None = None,
) -> str:
    """Log an error with optional stack trace."""
    meta = {"severity": severity}
    if stack:
        meta["stack"] = stack
    return _handle(
        get_store().append_entry,
        project_id,
        "error",
        title,
        body,
        tags,
        meta,
        "working",
        "agent",
        _session_id(),
        None,
        lock_token,
    )


@mcp.tool(structured_output=False)
def memory_add_file_ref(
    project_id: str,
    path: str,
    role: str,
    note: str | None = None,
    tags: list[str] | None = None,
    lock_token: str | None = None,
) -> str:
    """Reference a relevant file path."""
    body = note or ""
    meta = {"path": path, "role": role}
    t = tags or []
    t = list(t) + ["file"]
    return _handle(
        get_store().append_entry,
        project_id,
        "file_ref",
        f"{role}: {path}",
        body,
        t,
        meta,
        "persistent",
        "agent",
        _session_id(),
        None,
        lock_token,
    )


@mcp.tool(structured_output=False)
def memory_update_summary(
    project_id: str,
    summary: str | None = None,
    checkpoint: str | None = None,
    state_patch: dict | None = None,
    lock_token: str | None = None,
) -> str:
    """Update project summary, checkpoint, or state_json patch."""
    return _handle(
        get_store().update_summary,
        project_id,
        summary,
        checkpoint,
        state_patch,
        "agent",
        _session_id(),
        lock_token,
    )


@mcp.tool(structured_output=False)
def memory_search(
    project_id: str,
    query: str,
    types: list[str] | None = None,
    tags: list[str] | None = None,
    since: str | None = None,
    limit: int = 20,
    semantic: bool | None = None,
) -> str:
    """Hybrid FTS (+ optional semantic) search within a project."""
    return _handle(
        get_store().search,
        project_id,
        query,
        types,
        tags,
        since,
        limit,
        semantic,
    )


@mcp.tool(structured_output=False)
def memory_get_entry(entry_id: str) -> str:
    """Fetch a single memory entry by id."""
    return _handle(get_store().get_entry, entry_id)


@mcp.tool(structured_output=False)
def memory_update_entry(
    entry_id: str,
    title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    reason: str = "",
) -> str:
    """Update an entry (creates version history). Agent cannot set human_only."""
    return _handle(
        get_store().update_entry,
        entry_id,
        title,
        body,
        tags,
        metadata,
        reason,
        "agent",
        _session_id(),
    )


@mcp.tool(structured_output=False)
def memory_delete_entry(entry_id: str, reason: str, confirm: bool = False) -> str:
    """Soft-delete an entry. confirm must be true."""
    return _handle(
        get_store().delete_entry,
        entry_id,
        reason,
        confirm,
        "agent",
        _session_id(),
    )


@mcp.tool(structured_output=False)
def memory_export_project(project_id: str, format: str = "json") -> str:
    """Export project memory to local exports directory."""
    return _handle(get_store().export_project, project_id, format)


@mcp.tool(structured_output=False)
def memory_import_project(
    project_id: str,
    json_path: str,
    mode: str = "merge",
    confirm_overwrite: bool = False,
) -> str:
    """Import project from a JSON export file on disk."""
    from pathlib import Path

    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return _handle(
        get_store().import_project,
        data,
        mode,
        confirm_overwrite,
        "agent",
    )


@mcp.tool(structured_output=False)
def memory_acquire_lock(project_id: str, ttl_seconds: int = 120) -> str:
    """Acquire a write lease for a project."""
    store = get_store()
    holder = _session_id() or "agent"

    def _acquire():
        with store.db.transaction() as conn:
            store._require_active_project(conn, project_id, "agent")
            return store.locks.acquire(conn, project_id, holder, ttl_seconds)

    return _handle(_acquire)


@mcp.tool(structured_output=False)
def memory_release_lock(project_id: str, token: str) -> str:
    """Release a write lease."""

    def _release():
        with get_store().db.transaction() as conn:
            return get_store().locks.release(conn, project_id, token)

    return _handle(_release)


@mcp.tool(structured_output=False)
def memory_freeze_project(project_id: str, reason: str) -> str:
    """Freeze project (blocks agent writes). Prefer human via UI."""
    return _handle(get_store().freeze_project, project_id, reason, "agent")


@mcp.tool(structured_output=False)
def memory_get_agent_guide(client: str = "any") -> str:
    """Markdown guide: invoke MCP from Cline, Continue, Codex, or any local agent.
    client: cline | continue | codex | any"""
    return _handle(load_agent_guide, client)


@mcp.tool(structured_output=False)
def memory_list_audit_profiles() -> str:
    """List audit profile configs (searches, tasks, PoC rules, output dirs)."""
    return _handle(get_store().list_audit_profiles)


@mcp.tool(structured_output=False)
def memory_list_audit_prompts() -> str:
    """Índice de prompts (duplica prompts/list del protocolo MCP; preferir UI prompts del cliente)."""
    from mvp_memory.audit_profiles_loader import list_prompt_catalog

    catalog = list_prompt_catalog()
    native = mcp_prompt_names()
    return _handle(
        lambda: {
            "mcp_prompts_native": native,
            "hint": "En Cline/Cursor: panel Prompts MCP → audit-<profile_id> o guide-cline",
            "catalog": catalog,
        }
    )


@mcp.tool(structured_output=False)
def memory_get_audit_prompt(
    profile_id: str,
    target_directory: str | None = None,
) -> str:
    """Return full session prompt markdown + profile JSON config."""
    return _handle(get_store().get_audit_prompt, profile_id, target_directory)


@mcp.tool(structured_output=False)
def memory_audit_start(
    target_directory: str,
    profile_id: str = "security-baseline",
    output_dir: str | None = None,
    display_name: str | None = None,
    reset: bool = True,
) -> str:
    """One-call setup: auto project_id, plan, scans, output tree, tasks, session_prompt."""
    return _handle(
        get_store().audit_start,
        target_directory,
        profile_id=profile_id,
        output_dir=output_dir,
        display_name=display_name,
        reset=reset,
        actor="agent",
        session_id=_session_id(),
    )


@mcp.tool(structured_output=False)
def memory_audit_status(project_id: str) -> str:
    """Progress: output paths, next unit, open tasks, checkpoint."""
    return _handle(get_store().audit_status, project_id, "agent")


@mcp.tool(structured_output=False)
def memory_audit_next_step(project_id: str) -> str:
    """Next code unit + profile hints (read/scan) and output paths."""
    return _handle(get_store().audit_next_step, project_id, "agent")


@mcp.tool(structured_output=False)
def memory_audit_record_finding(
    project_id: str,
    severity: str,
    title: str,
    description: str = "",
    cwe: str | None = None,
    file_path: str | None = None,
    line: int | None = None,
    poc_markdown: str = "",
    evidence: str = "",
) -> str:
    """Write FIND-NNN-* under output_dir/findings/ and update indice.md (required for real results)."""
    return _handle(
        get_store().audit_record_finding,
        project_id,
        severity,
        title,
        description=description,
        cwe=cwe,
        file_path=file_path,
        line=line,
        poc_markdown=poc_markdown,
        evidence=evidence,
        actor="agent",
        session_id=_session_id(),
    )


@mcp.tool(structured_output=False)
def memory_audit_finalize(project_id: str) -> str:
    """Write RESUMEN-EJECUTIVO.md; verify findings exist on disk before declaring audit complete."""
    return _handle(get_store().audit_finalize, project_id, "agent")


@mcp.tool(structured_output=False)
def memory_audit_complete_step(
    project_id: str,
    unit_id: str,
    notes: str = "",
    skip: bool = False,
) -> str:
    """Mark plan unit done; updates checkpoint; returns next unit."""
    return _handle(
        get_store().audit_complete_step,
        project_id,
        unit_id,
        notes=notes,
        skip=skip,
        actor="agent",
        session_id=_session_id(),
    )


@mcp.tool(structured_output=False)
def memory_workspace_plan(
    project_id: str,
    auto_create: bool = True,
    profile: str = "security_code",
    reset: bool = False,
    workspace_path: str | None = None,
) -> str:
    """Scan project workspace_path; create one-file units for progressive security review."""
    return _handle(
        get_store().workspace_plan,
        project_id,
        profile=profile,
        reset=reset,
        workspace_path=workspace_path,
        auto_create=auto_create,
        actor="agent",
        session_id=_session_id(),
    )


@mcp.tool(structured_output=False)
def memory_workspace_next_unit(project_id: str) -> str:
    """Next pending workspace unit (paths, strategy, read budget)."""
    return _handle(get_store().workspace_next_unit, project_id, "agent")


@mcp.tool(structured_output=False)
def memory_workspace_read(
    project_id: str,
    rel_path: str,
    line_offset: int = 1,
    line_limit: int = 120,
    byte_offset: int = 0,
    byte_limit: int = 0,
    max_bytes: int = 48000,
) -> str:
    """Bounded read under workspace_path (lines or bytes for large minified files)."""
    return _handle(
        get_store().workspace_read,
        project_id,
        rel_path,
        line_offset=line_offset,
        line_limit=line_limit,
        byte_offset=byte_offset,
        byte_limit=byte_limit,
        max_bytes=max_bytes,
        actor="agent",
    )


@mcp.tool(structured_output=False)
def memory_workspace_complete_unit(
    project_id: str,
    unit_id: str,
    skip: bool = False,
) -> str:
    """Mark unit done/skipped; returns next pending unit."""
    return _handle(
        get_store().workspace_complete_unit,
        project_id,
        unit_id,
        skip=skip,
        actor="agent",
        session_id=_session_id(),
    )


@mcp.tool(structured_output=False)
def memory_workspace_scan_patterns(
    project_id: str,
    pattern: str,
    rel_path: str | None = None,
    max_count: int = 15,
) -> str:
    """Run bounded ripgrep; full output on disk under artifacts/, preview in response."""
    return _handle(
        get_store().workspace_scan_patterns,
        project_id,
        pattern,
        rel_path=rel_path,
        max_count=max_count,
        actor="agent",
    )


_REGISTERED_PROMPTS: list[str] = register_mcp_prompts(mcp)


def mcp_prompt_names() -> list[str]:
    """Nombres expuestos vía MCP prompts/list (tests/diagnóstico)."""
    return list(_REGISTERED_PROMPTS)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="MVP Memory Context MCP server (stdio)")
    parser.add_argument("--data-dir", default=None, help="Data directory for SQLite DB")
    parser.add_argument("--semantic", action="store_true", help="Enable hash-based semantic search")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    global _store, _settings
    _settings = Settings.from_args(data_dir=args.data_dir, semantic=args.semantic)
    _store = MemoryStore(_settings)

    if args.transport == "sse":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
