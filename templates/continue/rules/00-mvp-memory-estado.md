---
name: Memoria MCP — estado del proyecto
alwaysApply: true
description: Rehidratar y persistir estado con mvp-memory-context (checkpoint, no volcar JSON)
---

# Memoria de estado (MVP-memory-context)

## Identidad (sustituir en cada repo)

- **project_id:** `<ID_ESTABLE>` — mismo id en todas las sesiones de este clone.
- **workspace_path:** ruta absoluta de la raíz abierta en VS Code.

Obtener id sugerido:

```bash
cd /path/to/MVP-memory-context && source .venv/bin/activate
python -c "from mvp_memory.config import project_id_from_workspace; print(project_id_from_workspace('RUTA_REPO'))"
```

## Inicio de sesión (Agent)

1. **`memory_get_checkpoint`**(`project_id`, `auto_create: true` solo la primera vez).
2. Resume en **≤5 bullets**: summary, checkpoint, títulos de pendings/decisions — **sin pegar JSON** de la tool.
3. **No uses** `memory_get_state` con `compact: false` salvo depuración explícita.
4. **`memory_search`** solo si falta algo que no esté en el repo que vas a leer.

## Durante el trabajo

| Hecho | Tool |
|-------|------|
| Decisión / alcance estable | `memory_add_decision` |
| Tarea abierta por fases | `memory_add_pending` → `memory_resolve_pending` |
| Archivo clave creado o revisado | `memory_add_file_ref` (path relativo al workspace) |
| Error de entorno relevante | `memory_log_error` |

Detalle largo (logs, JSON, diffs) → **ficheros en disco**, no `memory_append_event` con cuerpos enormes.

## Fin de hito o sesión

1. **`memory_update_summary`**: summary de una línea + **checkpoint** corto (p.ej. `módulo:hecho; next:tarea-X`).
2. Opcional: `memory_acquire_lock` → escrituras → `memory_release_lock` si varias tools seguidas.

## Prohibido

- Inventar progreso no registrado en MCP o en el repo.
- `memory_delete_entry` sin confirmación explícita del usuario (`confirm: true`).
