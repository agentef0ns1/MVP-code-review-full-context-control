from __future__ import annotations

from pathlib import Path

_GUIDE_PATH = Path(__file__).resolve().parent / "prompts" / "agent_guide.md"

_CLIENT_SECTIONS = {
    "cline": """
## Sesión Cline (acción inmediata)

1. Verifica MCP conectado (tools `memory_*` visibles).
2. `memory_get_checkpoint(project_id="<ID>", auto_create=true)`.
3. `memory_create_project(..., workspace_path="/ruta/codigo")` si hace falta.
4. `memory_workspace_plan(project_id="<ID>", reset=true)`.
5. Bucle: `memory_workspace_next_unit` → `memory_workspace_read` / `memory_workspace_scan_patterns` → informe en disco → `memory_workspace_complete_unit` + `memory_update_summary`.
6. No uses Read del IDE sobre `main.*.js` / `vendor*.js`; usa tools MCP.
""",
    "continue": """
## Sesión Continue (acción inmediata)

1. MCP stdio según `templates/continue/mcpServers/mvp-memory-context.json`.
2. **No** dependas de prompts MCP nativos; usa esta tool `memory_get_agent_guide`.
3. Reglas `templates/continue/rules/00-mvp-memory-estado.md`.
4. Mismo bucle workspace_plan → read/scan → complete_unit.
5. Auto-approve: `memory_get_agent_guide`, `memory_workspace_*`, `memory_get_checkpoint`.
""",
    "codex": """
## Agente local / Codex / CLI MCP

1. Servidor: `scripts/run-mcp.sh` o `mvp-memory-mcp --data-dir ~/.local/share/mvp-memory-context`.
2. Cliente stdio apuntando al mismo comando.
3. `memory_get_agent_guide(client="codex")` al inicio de cada sesión.
4. `MVP_MEMORY_DATA_DIR` unificado entre API y MCP si usas panel web.
5. Bucle plan/read/complete; artefactos rg en `$DATA_DIR/artifacts/<project_id>/`.
""",
}


def load_agent_guide(client: str = "any") -> dict:
    base = _GUIDE_PATH.read_text(encoding="utf-8") if _GUIDE_PATH.is_file() else ""
    key = client.lower().strip()
    extra = _CLIENT_SECTIONS.get(key, _CLIENT_SECTIONS.get("cline", ""))
    if key == "any":
        extra = "\n".join(_CLIENT_SECTIONS.values())
    text = base.strip() + "\n\n---\n" + extra.strip() + "\n"
    return {
        "client": key,
        "format": "markdown",
        "guide": text,
        "approx_tokens": len(text) // 4,
        "source": str(_GUIDE_PATH),
    }
