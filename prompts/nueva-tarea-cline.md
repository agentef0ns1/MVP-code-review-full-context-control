# Prompt de usuario — nueva tarea en Cline (MVP Memory Context)

Copia el bloque siguiente **como primer mensaje** en Cline cuando abras un workspace con el MCP `mvp-memory-context` ya configurado.

Sustituye los valores entre `<…>` antes de enviar.

---

## Plantilla (nueva tarea)

```text
Usa el MCP mvp-memory-context para memoria persistente de este proyecto.

project_id: <ID_ESTABLE>
workspace_path: <RUTA_ABSOLUTA_DEL_REPO>

Antes de planificar o tocar código:
1. Llama a memory_get_state(project_id, auto_create=true) y resume en 5 bullets lo que ya existe (summary, checkpoint, pendientes, decisiones).
2. Si falta detalle, usa memory_search(project_id, query=...) — no inventes contexto que no esté en memoria ni en el repo que leas.

Mi tarea en esta sesión:
- Objetivo: <QUÉ_QUIERO_LOGRAR>
- Alcance: <CARPETAS_O_MÓDULOS_INCLUIDOS>
- Fuera de alcance: <QUÉ_NO_TOCAR>
- Criterio de hecho: <CÓMO_SÉ_QUE_ESTÁ_TERMINADO>
- Prioridad: <alta|media|baja>

Reglas de memoria:
- Al definir alcance o criterios importantes: memory_add_decision.
- Si la tarea tiene fases: memory_add_pending por fase y ciérralas con memory_resolve_pending al terminar.
- Al cerrar un hito (no cada archivo): memory_acquire_lock → memory_append_event + memory_update_summary (summary compacto + checkpoint=<hito>) → memory_release_lock.
- Errores relevantes: memory_log_error.
- Archivos clave analizados: memory_add_file_ref.
- No uses memory_delete_entry salvo que yo confirme explícitamente; entonces confirm=true.

Empieza confirmando el project_id, el checkpoint actual y tu plan en 3–5 pasos. Luego ejecuta.
```

---

## Plantilla (continuar tarea / sesión nueva)

```text
Continúo el mismo proyecto con memoria MCP.

project_id: <ID_ESTABLE>
workspace_path: <RUTA_ABSOLUTA_DEL_REPO>

1. memory_get_state(project_id) — reanuda desde checkpoint y pendientes abiertos; no repitas trabajo ya registrado en memoria.
2. memory_search si necesitas contexto de decisiones o errores previos.

En esta sesión quiero: <QUÉ_SIGUE_AHORA>

Al terminar la sesión deja memoria actualizada (checkpoint + evento de cierre) con lock.
```

---

## Cómo obtener `project_id`

Desde el repo del workspace:

```bash
cd /path/to/MVP-code-analisys-full-context-control
source .venv/bin/activate
python -c "from mvp_memory.config import project_id_from_workspace; print(project_id_from_workspace('RUTA_A_TU_REPO'))"
```

Usa **siempre el mismo** `project_id` para ese clone del repo.

---

## Ejemplo rellenado (este monorepo Tools)

```text
Usa el MCP mvp-memory-context para memoria persistente de este proyecto.

project_id: tools-a1b2c3
workspace_path: /path/to/your/workspace

Antes de planificar o tocar código:
1. Llama a memory_get_state("tools-a1b2c3", auto_create=true) y resume en 5 bullets lo que ya existe.
2. Si falta detalle, memory_search — no inventes contexto.

Mi tarea en esta sesión:
- Objetivo: Revisar que MVP-memory-context cumple el plan y documentar el prompt de Cline.
- Alcance: MVP-memory-context/, README, prompts/
- Fuera de alcance: MCP-kali, Agent-lab
- Criterio de hecho: README + prompts/nueva-tarea-cline.md listos; tests pasan.
- Prioridad: media

Reglas de memoria: (las de la plantilla estándar)

Empieza con checkpoint actual y plan en 3–5 pasos.
```

*(Sustituye `tools-a1b2c3` por el id real que devuelva `project_id_from_workspace`.)*

---

## Consejo Cline

- Activa el servidor MCP en **Configure → MCP Servers** y comprueba que `mvp-memory-context` aparece conectado antes de pegar el prompt.
- Para tareas largas, abre cada sesión nueva con la plantilla **continuar tarea**.
- Supervisión humana: `./scripts/run-api.sh` → http://127.0.0.1:8765
