"""Texto de ejemplos concretos embebido en prompts MCP."""
from __future__ import annotations

from pathlib import Path

from mvp_memory.audit_profiles_loader import slug_from_path

_DEFAULT_TARGET = "/path/to/your/repository"


def invocation_block(
    target_directory: str,
    profile_id: str,
    project_id: str | None = None,
) -> str:
    target = target_directory.strip() or _DEFAULT_TARGET
    root = Path(target)
    pid = project_id or slug_from_path(root)
    out = f"{target}/.mvp-audit"
    return f"""
## Invocación concreta (copiar en tools MCP)

### 1. Arranque
```
memory_audit_start(
  target_directory="{target}",
  profile_id="{profile_id}",
  output_dir=".mvp-audit",
  reset=true
)
```
→ Guarda `project_id` (esperado: `{pid}`) y `output_dir` (`{out}`).

### 2. Siguiente paso
```
memory_audit_next_step(project_id="{pid}")
```

### 3. Leer init.js (ejemplo)
```
memory_workspace_read(
  project_id="{pid}",
  rel_path="init.js",
  line_limit=120
)
```

### 4. Registrar hallazgo (obligatorio en disco)
```
memory_audit_record_finding(
  project_id="{pid}",
  severity="high",
  title="Descripción corta",
  cwe="CWE-79",
  file_path="init.js",
  line=40,
  description="Qué ocurre",
  evidence="snippet",
  poc_markdown="Pasos PoC"
)
```

### 5. Cerrar unidad
```
memory_audit_complete_step(
  project_id="{pid}",
  unit_id="chunk-0001",
  notes="Unidad revisada"
)
```

### 6. Finalizar
```
memory_audit_finalize(project_id="{pid}")
```

Documentación completa: ver prompt `audit-orchestration` o `src/mvp_memory/prompts/audit_orchestration.md`.
"""


def quickstart_prompt(target_directory: str, profile_id: str) -> str:
    target = target_directory.strip() or _DEFAULT_TARGET
    root = Path(target)
    pid = slug_from_path(root)
    return f"""# Auditoría — inicio rápido

Ruta objetivo: `{target}`  
Perfil: `{profile_id}`  
project_id esperado: `{pid}`

## Orden estricto

1. **memory_audit_start** — ver bloque abajo  
2. **memory_audit_next_step** — repetir bucle  
3. **memory_workspace_read** / **memory_workspace_scan_patterns** — nunca volcar bundles al chat  
4. **memory_audit_record_finding** — un call por hallazgo (FIND-* en disco)  
5. **memory_audit_complete_step** — tras cada chunk  
6. **memory_audit_finalize** — antes de decir "completo"

{invocation_block(target, profile_id, pid)}

## Regla
Resumen en chat ≠ auditoría. Comprueba `{target}/.mvp-audit/findings/FIND-*` y RESUMEN-EJECUTIVO.md.
"""
