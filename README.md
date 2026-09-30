# MVP Memory Context

Auditoría de código en local para modelos con ventana de contexto corta. El servidor MCP recorre cualquier ruta del sistema, guarda el estado en SQLite y escribe el informe en disco. El modelo no pagina el repositorio.

## El problema

Un agente local (Ollama, Cline, Continue, Cursor) sobre un árbol grande se queda sin contexto: vuelca ficheros enteros, repite la misma tool y la tarea se corta. Un `unit_id` como `chunk-0001` no es una carpeta. Pegar el repo en el chat no es el flujo.

## Arquitectura

El servidor es el bucle. El modelo lanza una tool y recibe una respuesta corta.

```text
Usuario → agente (Cline / Cursor / Continue)
              │
              │  memory_audit_run(ruta, perfil)
              ▼
         Servidor MCP
              │
              ├─ plan de unidades (SQLite)
              ├─ lectura acotada o rg por unidad
              ├─ fallo → .mvp-audit/INCIDENTES.md y sigue
              └─ cierre → .mvp-audit/RESUMEN-EJECUTIVO.md
```

![Componentes del análisis de código con control de contexto MCP](MVP-context-code-analysis.png)

| Pieza | Dónde vive | Qué hace |
|-------|------------|----------|
| Plan | SQLite en `~/.local/share/mvp-memory-context/` | Una unidad por fichero. `chunk-0001` es un id, no una ruta. |
| Recorrido | `memory_audit_run` | Lee o escanea cada unidad. Si falla, la salta y continúa. |
| Patrones | `<ruta>/.mvp-audit/scans/` | Secretos, sinks, XSS, SQLi y el resto del perfil. No vuelven al chat. |
| Informe | `<ruta>/.mvp-audit/RESUMEN-EJECUTIVO.md` | Cierre, aunque no haya hallazgos. |
| Revisión posterior | `<ruta>/.mvp-audit/INCIDENTES.md` | Ficheros que no se pudieron leer. |

La respuesta de `memory_audit_run` cabe en unos 2 KB: `done`, `project_id`, contadores y las dos rutas. No incluye el código, ni el catálogo de patrones, ni el prompt de sesión.

Si el cliente corta la tool por tiempo, el progreso queda en SQLite. Otra llamada con el mismo `project_id` continúa donde se quedó y no rehace las unidades ya cerradas.

`memory_audit_next_step` y `memory_workspace_read` siguen en el servidor para depurar una unidad. El camino normal no los usa.

![Flujo de comunicación agente, LLM, MCP y repositorio](MVP-context-code-analisys-flow.png)

## 1. Instalación

```bash
git clone https://github.com/agentef0ns1/MVP-code-review-full-context-control.git
cd MVP-code-review-full-context-control
chmod +x scripts/*.sh
./scripts/install.sh
```

Datos del servidor: `~/.local/share/mvp-memory-context/`. Se crean al usarlo.

## 2. Inspector

```bash
./scripts/run-mcp-inspector.sh
```

Prueba el prompt `audit-quickstart` y la tool `memory_audit_run`.

![MCP Inspector — listado de tools y prompts del servidor](MVP-inspector.png)

## 3. Cline

Archivo: `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

Ajusta `command` a tu clon y a tu `.venv`.

```json
{
  "mcpServers": {
    "mvp-memory-context": {
      "command": "/ruta/al/clon/.venv/bin/python",
      "args": [
        "-m", "mvp_memory.mcp_server",
        "--data-dir", "/home/USER/.local/share/mvp-memory-context"
      ]
    }
  }
}
```

Recarga el editor, activa **mvp-memory-context** y aprueba la tool. Usa un solo servidor para cada ruta. Otro proceso MCP con su propia base SQLite no comparte el mismo `project_id`.

Cursor, Continue, SSE y el panel web: [`docs/other-configs.md`](docs/other-configs.md).

![Cline ejecutando auditoría vía MCP](MVP-cline.png)

## 4. Prompts

Sustituye la ruta. Un mensaje nuevo, solo este servidor.

Arranque:

```text
Usa solo el MCP mvp-memory-context. memory_audit_run(target_directory="/RUTA/DEL/CODIGO", profile_id="security-full", reset=true). No uses read_files, ls ni find. No pares hasta que la respuesta traiga done=true y la ruta de RESUMEN-EJECUTIVO.md.
```

Si la tarea se para, por el motivo que sea:

```text
No repitas la última tool. memory_audit_run(project_id="<id>"). Si done es true, termina. Los fallos están en INCIDENTES.md.
```

El `project_id` sale en la primera respuesta. Si no lo tienes, el directorio analizado ya está en la tarea: pide `memory_audit_status` de ese proyecto y sigue con `memory_audit_run`.

Prompts del Inspector, además del texto de arriba:

| Prompt | Uso |
|--------|-----|
| `audit-quickstart` | Arranque corto de una auditoría. |
| `audit-orchestration` | Protocolo de depuración unidad a unidad. |
| `audit-<profile_id>` | Prompt del perfil, por ejemplo `audit-security-full`. |
| `guide-cline` | Guía del cliente Cline. También `guide-continue` y `guide-codex`. |

## 5. Perfiles

JSON en [`src/mvp_memory/audit_profiles/`](src/mvp_memory/audit_profiles/). Algunos usan `extends`.

| `profile_id` | Uso |
|--------------|-----|
| `security-baseline` | Recorrido progresivo, secretos, storage y sinks. |
| `security-static-first` | Semgrep y gitleaks si están instalados; luego el alcance amplio. |
| `security-injection` | XSS, SQLi, SSRF y validación débil. |
| `js-console-api` | APIs expuestas en `window` y en la consola del navegador. |
| `security-full` | Baseline, consola e inyecciones. |

Listar en runtime: `memory_list_audit_profiles`.

## 6. Tools

Camino normal:

| Tool | Uso |
|------|-----|
| `memory_audit_run` | Recorre la ruta, salta fallos, escribe el resumen. `target_directory` empieza; `project_id` reanuda. |
| `memory_audit_status` | Progreso, ruta de salida y checkpoint. |
| `memory_list_audit_profiles` | Catálogo de perfiles. |
| `memory_get_audit_prompt` | Texto y JSON de un perfil. |
| `memory_get_agent_guide` | Guía según el cliente. |
| `memory_audit_record_finding` | Hallazgo confirmado en `findings/FIND-*/`. |

Depuración, no hace falta para terminar el informe:

| Tool | Uso |
|------|-----|
| `memory_audit_start` | Crea proyecto, plan y scans sin recorrer las unidades. |
| `memory_audit_next_step` | Siguiente unidad, respuesta corta (`do_now`, `then`). |
| `memory_audit_complete_step` | Cierra una unidad a mano. |
| `memory_audit_finalize` | Regenera `RESUMEN-EJECUTIVO.md`. |
| `memory_workspace_plan` | Rehace el plan de ficheros. |
| `memory_workspace_next_unit` | Siguiente unidad pendiente. Devuelve `read_rel_path` exacto. |
| `memory_workspace_read` | Lectura acotada. `chunk-0001/fichero` se corrige al `read_rel_path` real si ese fichero existe. |
| `memory_workspace_scan_patterns` | `rg` de un patrón hacia `.mvp-audit/scans/`. |
| `memory_workspace_complete_unit` | Marca la unidad hecha o saltada. |

Memoria de proyecto, locks, export/import y el listado completo: [`docs/other-configs.md`](docs/other-configs.md).

## 7. Qué queda en disco

Dentro de la ruta analizada, en `.mvp-audit/`:

| Fichero | Contenido |
|---------|-----------|
| `RESUMEN-EJECUTIVO.md` | Cierre y sección «Pendiente de revisión». |
| `INCIDENTES.md` | Unidades saltadas y el error. |
| `scans/` | Patrones del perfil e `INDICE-UNIDADES.md`. |
| `findings/` | Hallazgos registrados con `memory_audit_record_finding`. |
| `unidades/` | Notas por unidad, si se usó el modo de depuración. |

El modelo no tiene que haber leído ningún fichero para que el resumen exista.
