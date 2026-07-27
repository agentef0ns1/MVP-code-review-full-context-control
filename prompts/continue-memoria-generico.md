# Continue + MVP Memory Context (VS Code)

Objetivo: que **Continue en Agent mode** rehidrated y persista **estado del proyecto** vía MCP, con poco contexto.  
No depende de scripts de campaña ni de un TFM concreto.

## 1. Instalar MCP (una vez)

```bash
cd /path/to/MVP-memory-context
./scripts/install.sh
```

Datos: `~/.local/share/mvp-memory-context/memory.db`

## 2. Por cada repo / workspace

```bash
./scripts/scaffold-continue-project.sh /ruta/absoluta/al/repo TU_PROJECT_ID
```

Copia:

- `.continue/mcpServers/mvp-memory-context.json` (stdio + **autoApprove** memory_*)
- `.continue/rules/01-mvp-memory-estado.md` (con tu `project_id` y workspace)
- `.continue/rules/02-contexto-minimo.md`

Abre **VS Code** en esa carpeta (no el monorepo padre si no hace falta).

## 3. Config global Continue (`~/.continue/config.yaml`)

- **Modelos** en Main Config.
- **No** pongas `mvp-memory-context` también en Main Config **y** en el workspace → doble conexión / timeout.
- Solo **un** registro MCP por nombre: preferible **por workspace** (JSON del scaffold).

## 4. UI Continue (una vez por perfil)

1. **Agent mode** + modelo con **tool_use**.
2. Icono **Tools** → **mvp-memory-context** → política **Automatic** (solo tools MCP).
3. Icono **Tools** → **Run Terminal Command** → **Automatic** (shell; **independiente** del MCP).
4. Icono **Rules** → activar reglas del proyecto.
5. Tras cambiar MCP: **MCP: Reset Cached Tools** → Reload Window.

**Permisos de terminal:** MCP en Automatic **no** desactiva el popup **Run Terminal Command**. Continue trata intérpretes (`python3`, `bash`, …) como alto riesgo; muchos comandos piden Accept aunque la política sea Automatic ([issue #10512](https://github.com/continuedev/continue/issues/10512)). Los ajustes `chat.tools.terminal.*` de VS Code son de **Copilot**, no de Continue. Para flujo memoria-first, evita bash: **`memory_get_checkpoint`** + **`memory_update_summary`** en lugar de scripts de estado.

## 5. Flujo de memoria (lo que debe hacer el agente)

```
Sesión nueva:
  memory_get_checkpoint(project_id, auto_create=true si 1ª vez)
  → resume ≤5 bullets
  → trabajar en repo
  → memory_add_file_ref / decisions / pendings según hitos
  → memory_update_summary(checkpoint corto)

Sesión siguiente:
  memory_get_checkpoint(auto_create=false)
  → continuar desde checkpoint, no repetir trabajo
```

**Lectura:** `memory_get_checkpoint` (compacto).  
**Guía clientes:** `memory_get_agent_guide(client="continue")`.  
**Código grande:** `memory_workspace_plan` + `memory_workspace_read`.  
**Evitar:** `memory_get_state` full en chat.

## 6. Prompt mínimo (pegar en Continue)

### Nueva sesión

```text
Memoria MCP activa. project_id: "TU_PROJECT_ID"
workspace: /ruta/absoluta/repo

1. memory_get_checkpoint (auto_create true si vacío)
2. Resume estado en 5 bullets; no pegues JSON
3. Objetivo hoy: <describe en una frase>

Sigue rules del proyecto. Agent mode.
```

### Continuar

```text
Continúo project_id "TU_PROJECT_ID".
memory_get_checkpoint (auto_create false) → 3 bullets → sigo con: <tarea>
Al cerrar: memory_update_summary + checkpoint corto.
```

## 7. Panel humano (opcional)

```bash
./scripts/run-api.sh   # http://127.0.0.1:8765
```

## 8. Otros IDEs

- **Cline:** `prompts/nueva-tarea-cline.md`
- **Cursor:** mismo JSON MCP; rules en `.cursor/rules` si aplica

El caso TFM (`attacker-agent`) añade rules de campaña **opcionales**; la memoria MCP es la misma.
