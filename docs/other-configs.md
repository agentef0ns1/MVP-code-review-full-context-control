# Otras configuraciones y referencia

Complemento del [README](../README.md): clientes alternativos, panel admin, flujos de memoria y detalle de tools.

## MCP stdio (sin Inspector)

```bash
./scripts/run-mcp.sh
```

## Cursor

Mismo JSON que Cline en `~/.cursor/mcp.json`.

## Continue + VS Code

Guía: [`prompts/continue-memoria-generico.md`](../prompts/continue-memoria-generico.md)

```bash
./scripts/scaffold-continue-project.sh /ruta/absoluta/al/repo TU_PROJECT_ID
```

Plantilla: [`templates/continue/mcpServers/mvp-memory-context.json`](../templates/continue/mcpServers/mvp-memory-context.json)

Flujo memoria: `memory_get_checkpoint` → trabajo → `memory_update_summary` / `memory_add_file_ref`.

### Continue (YAML legacy)

```yaml
name: mvp-memory-context
version: 0.2.0
schema: v1
mcpServers:
  - name: mvp-memory-context
    command: /ruta/al/clon/.venv/bin/python
    args:
      - -m
      - mvp_memory.mcp_server
      - --data-dir
      - /home/USER/.local/share/mvp-memory-context
    env: {}
```

## MCP SSE (opcional)

```bash
./scripts/run-mcp.sh --transport sse --host 127.0.0.1 --port 8766
```

## Búsqueda semántica local

```bash
./scripts/run-mcp.sh --semantic
# o
export MVP_MEMORY_SEMANTIC=1
```

## Panel web de administración

```bash
./scripts/run-api.sh
```

http://127.0.0.1:8765 — token en `~/.config/mvp-memory-context/admin.token` (se crea al arrancar la API).

Funciones: proyectos, timeline, búsqueda, export/import, auditoría, congelar proyecto, locks.

## Identificador de proyecto

Se genera en `memory_audit_start(target_directory=...)`.  
Manual: `python -c "from mvp_memory.config import project_id_from_workspace; print(project_id_from_workspace('/ruta/repo'))"`

## Bucle de auditoría (detalle)

```text
memory_list_audit_profiles()
memory_get_audit_prompt("js-console-api", "/ruta/codigo")   # opcional

memory_audit_start(
  target_directory="/ruta/absoluta/al/codigo",
  profile_id="security-baseline",
  output_dir=".mvp-audit"
)

memory_audit_next_step → memory_workspace_read / scan_patterns → LLM
→ memory_audit_record_finding
→ memory_audit_complete_step
→ repetir
→ memory_audit_finalize
```

Prompts MCP: `audit-quickstart`, `audit-orchestration`, `audit-<profile_id>`.  
Tools: `memory_list_audit_prompts`, `memory_get_audit_prompt`.

Plantilla tarea Cline: [`prompts/nueva-tarea-cline.md`](../prompts/nueva-tarea-cline.md)

## Disciplina del agente (memoria)

1. Inicio: `memory_get_checkpoint` o `memory_get_agent_guide`.
2. No inventar contexto; `memory_search` si hace falta.
3. Hito: `memory_acquire_lock` → update → `memory_update_summary` → `memory_release_lock`.
4. `memory_delete_entry` solo con `confirm=true` y OK del usuario.

## Escenarios

**Codebase grande:** `memory_audit_start`; tools `memory_workspace_*` para control fino.

**Tarea larga (deriva):** `memory_add_pending`, `memory_resolve_pending`, `memory_append_event`, `memory_log_error`, checkpoint en `memory_update_summary`; congelar desde el panel si hay bucle.

## Tools MCP (listado completo)

| Tool | Uso |
|------|-----|
| `memory_list_projects` | Listado |
| `memory_create_project` | Alta explícita |
| `memory_get_state` / `memory_get_checkpoint` | Estado / reanudación |
| `memory_audit_*` | Sesión de auditoría (ver README) |
| `memory_workspace_plan` / `next_unit` / `read` / `complete_unit` / `scan_patterns` | Plan y lectura acotada |
| `memory_list_audit_profiles` / `memory_list_audit_prompts` / `memory_get_audit_prompt` | Perfiles y prompts |
| `memory_get_agent_guide` | Guía por cliente |
| `memory_append_event` | Hitos |
| `memory_add_decision` / `memory_add_pending` / `memory_log_error` / `memory_add_file_ref` | Entradas tipadas |
| `memory_resolve_pending` | Cerrar pendiente |
| `memory_update_summary` | Resumen y checkpoint |
| `memory_search` | FTS (+ semántica opcional) |
| `memory_get_entry` / `memory_update_entry` / `memory_delete_entry` | CRUD |
| `memory_export_project` / `memory_import_project` | Backup |
| `memory_acquire_lock` / `memory_release_lock` | Concurrencia |
| `memory_freeze_project` | Solo lectura para agente |

`memory_purge_entry` solo vía API admin.

## SQLCipher (opcional)

`MVP_MEMORY_SQLCIPHER=1` reserva el flag; cifrado en reposo pendiente de integrar `sqlcipher` en una versión posterior.

## Tests

```bash
source .venv/bin/activate
pytest
```

## Estructura del repo

```
├── migrations/
├── src/mvp_memory/
│   ├── core/
│   ├── mcp_server/
│   └── api/
├── tests/
├── scripts/
└── docs/
```


