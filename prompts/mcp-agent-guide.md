# Prompts MCP (servidor)

## En el cliente (Cline / Inspector)

Panel **Prompts** del servidor — **no hace falta** `memory_list_audit_prompts`:

| Prompt | Contenido |
|--------|-----------|
| **`audit-quickstart`** | Pasos 1–6 con calls reales (`memory_audit_start`, …) |
| **`audit-orchestration`** | Pseudocódigo + diagrama mermaid + componentes |
| **`audit-security-static-first`** | Perfil + bloque de invocación |
| **`audit-security-full`** | Perfil completo + ejemplos |
| **`guide-cline`** | Config MCP VS Code |

Argumentos útiles en perfiles `audit-*`: `target_directory=/path/to/your/repository`

## Ejemplo mínimo

```
memory_audit_start(
  target_directory="/path/to/your/repository",
  profile_id="security-static-first",
  reset=true
)
```

## Inspector

```bash
./scripts/run-mcp-inspector.sh
```

Doc en repo: [`src/mvp_memory/prompts/audit_orchestration.md`](../src/mvp_memory/prompts/audit_orchestration.md)
