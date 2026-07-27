---
name: Contexto mínimo MCP
alwaysApply: true
description: No llenar el chat con respuestas JSON de memoria MCP
---

# Presupuesto de contexto

- Respuestas de tools MCP: **resumen breve**, nunca JSON completo en el chat.
- Preferir **`memory_get_checkpoint`** frente a `memory_get_state`.
- Inicio de sesión: **`memory_get_agent_guide(client="continue")`**.
- Código grande: **`memory_workspace_read`** / **`memory_workspace_scan_patterns`** — no Read del IDE sobre bundles.
- Si una tool MCP falla (timeout/aborted): **un reintento**; luego `memory_log_error` y sigue con el repo local.
