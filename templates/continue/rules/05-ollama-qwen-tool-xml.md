---
name: Ollama Qwen — tool XML
alwaysApply: true
description: Evitar errores Ollama al parsear tool calls (function/parameter, XML mal cerrado)
---

# Tool calls con Ollama + Qwen (Continue Agent)

Ollama parsea tools en **XML Qwen**. Evita:

- `expected element type <function> but have <parameter>`
- `XML syntax error: element <function> closed by </parameter>`

## Reglas

1. **Una tool por turno** del asistente.
2. Cierra cada `<parameter=…>…</parameter>` **antes** de `</function>`.
3. Sin `<` en valores; strings cortos y en una línea.
4. Tras error XML: reintenta una tool mínima (p. ej. `memory_get_checkpoint` solo con `project_id`).

Plantilla:

```text
<tool_call>
<function=memory_get_checkpoint>
<parameter=project_id>TU_PROJECT_ID</parameter>
</function>
</tool_call>
```
