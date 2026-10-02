# Ejemplos de Prompts para Auditorías

Prompts de ejemplo para ejecutar auditorías con LLM local. Sustituye las rutas con tus directorios reales.

## Formato General

```text
Usa solo el MCP mvp-memory-context. memory_audit_run(target_directory="/ruta/a/tu/codigo", profile_id="<perfil>", reset=true). No uses read_files, ls ni find. No pares hasta que la respuesta traiga done=true y la ruta de RESUMEN-EJECUTIVO.md.
```

## Ejemplos por Perfil

### security-baseline (Auditoría Rápida)

**Descripción**: Escaneo rápido de secretos, almacenamiento cliente y sinks peligrosos.  
**Duración**: 30 segundos - 4 minutos  
**Patrones**: 3 (secrets, storage, sinks)

```text
Usa solo el MCP mvp-memory-context. memory_audit_run(target_directory="/home/usuario/proyectos/mi-app", profile_id="security-baseline", reset=true). No uses read_files, ls ni find. No pares hasta que la respuesta traiga done=true y la ruta de RESUMEN-EJECUTIVO.md.
```

**Casos de uso**:
- Primera auditoría rápida
- Validación después de cambios
- CI/CD con tiempo limitado

---

### security-injection (Vulnerabilidades de Inyección)

**Descripción**: Detecta XSS, SQLi, SSRF, command injection, path traversal, etc.  
**Duración**: 1-4 minutos  
**Patrones**: 9 especializados

```text
Usa solo el MCP mvp-memory-context. memory_audit_run(target_directory="/home/usuario/proyectos/api-backend", profile_id="security-injection", reset=true). No uses read_files, ls ni find. No pares hasta que la respuesta traiga done=true y la ruta de RESUMEN-EJECUTIVO.md.
```

**Casos de uso**:
- Aplicaciones web con forms
- APIs que procesan input del usuario
- Apps con queries SQL/NoSQL

---

### js-console-api (APIs de Consola JavaScript)

**Descripción**: Cataloga APIs accesibles desde DevTools (window, globalThis, exports).  
**Duración**: 30 segundos - 4 minutos  
**Patrones**: 4 (window.*, window["*"], globalThis, exports)

```text
Usa solo el MCP mvp-memory-context. memory_audit_run(target_directory="/home/usuario/proyectos/frontend-spa", profile_id="js-console-api", reset=true). No uses read_files, ls ni find. No pares hasta que la respuesta traiga done=true y la ruta de RESUMEN-EJECUTIVO.md.
```

**Casos de uso**:
- Aplicaciones SPA (React, Vue, Angular)
- Mapeo de superficie de ataque
- Pentesting desde navegador

---

### security-full (Auditoría Completa sin Herramientas Externas)

**Descripción**: Combinación de baseline + injection + console (16 patrones).  
**Duración**: 2-6 minutos  
**Patrones**: 16 (todos los anteriores combinados)

```text
Usa solo el MCP mvp-memory-context. memory_audit_run(target_directory="/home/usuario/proyectos/webapp-completa", profile_id="security-full", reset=true). No uses read_files, ls ni find. No pares hasta que la respuesta traiga done=true y la ruta de RESUMEN-EJECUTIVO.md.
```

**Casos de uso**:
- Auditoría exhaustiva
- Antes de producción
- Revisión de seguridad completa

---

### security-static-first (Con Semgrep y Gitleaks)

**Descripción**: Ejecuta semgrep/gitleaks primero, luego 16 patrones regex.  
**Duración**: 3-10 minutos  
**Patrones**: Herramientas estáticas + 16 regex  
**Requisitos**: semgrep y gitleaks instalados

```text
Usa solo el MCP mvp-memory-context. memory_audit_run(target_directory="/home/usuario/proyectos/app-produccion", profile_id="security-static-first", reset=true). No uses read_files, ls ni find. No pares hasta que la respuesta traiga done=true y la ruta de RESUMEN-EJECUTIVO.md. Revisa static/README.md para ver el status de semgrep y gitleaks.
```

**Casos de uso**:
- Integración CI/CD
- Máxima cobertura
- Proyectos con git inicializado

---

## Reanudación de Auditoría Interrumpida

Si el LLM se detiene antes de completar:

```text
No repitas la última tool. memory_audit_run(project_id="<id>"). Si done es true, termina. Los fallos están en INCIDENTES.md.
```

**Ejemplo**:
```text
No repitas la última tool. memory_audit_run(project_id="webapp-a1b2c3"). Si done es true, termina. Los fallos están en INCIDENTES.md.
```

---

## Estructura de Directorios de Ejemplo

### Proyecto Frontend
```
/home/usuario/proyectos/mi-spa/
├── src/
│   ├── components/
│   ├── services/
│   └── utils/
├── public/
└── package.json
```

**Prompt**:
```text
memory_audit_run(target_directory="/home/usuario/proyectos/mi-spa", profile_id="js-console-api", reset=true)
```

### Proyecto Backend
```
/home/usuario/proyectos/api-rest/
├── controllers/
├── models/
├── routes/
└── middleware/
```

**Prompt**:
```text
memory_audit_run(target_directory="/home/usuario/proyectos/api-rest", profile_id="security-injection", reset=true)
```

### Proyecto Fullstack
```
/home/usuario/proyectos/ecommerce/
├── frontend/
├── backend/
└── shared/
```

**Opción A - Auditar todo**:
```text
memory_audit_run(target_directory="/home/usuario/proyectos/ecommerce", profile_id="security-full", reset=true)
```

**Opción B - Auditar por separado**:
```text
# Frontend
memory_audit_run(target_directory="/home/usuario/proyectos/ecommerce/frontend", profile_id="js-console-api", reset=true)

# Backend
memory_audit_run(target_directory="/home/usuario/proyectos/ecommerce/backend", profile_id="security-injection", reset=true)
```

---

## Verificación de Resultados

### Ver resumen ejecutivo
```bash
cat /home/usuario/proyectos/mi-app/.mvp-audit/RESUMEN-EJECUTIVO.md
```

### Verificar incidentes
```bash
test -f /home/usuario/proyectos/mi-app/.mvp-audit/INCIDENTES.md && \
  cat /home/usuario/proyectos/mi-app/.mvp-audit/INCIDENTES.md || \
  echo "✓ No hubo incidentes"
```

### Listar scans generados
```bash
ls /home/usuario/proyectos/mi-app/.mvp-audit/scans/
```

### Ver estado de herramientas estáticas (solo security-static-first)
```bash
cat /home/usuario/proyectos/mi-app/.mvp-audit/static/README.md
```

---

## Ejemplo Completo de Flujo

### 1. Auditoría inicial rápida
```text
Usa solo el MCP mvp-memory-context. memory_audit_run(target_directory="/home/usuario/proyectos/nueva-app", profile_id="security-baseline", reset=true). No uses read_files, ls ni find. No pares hasta que la respuesta traiga done=true y la ruta de RESUMEN-EJECUTIVO.md.
```

### 2. Revisar resultados
```bash
cat /home/usuario/proyectos/nueva-app/.mvp-audit/RESUMEN-EJECUTIVO.md
cat /home/usuario/proyectos/nueva-app/.mvp-audit/scans/secrets.txt
```

### 3. Auditoría completa
```text
Usa solo el MCP mvp-memory-context. memory_audit_run(target_directory="/home/usuario/proyectos/nueva-app", profile_id="security-full", reset=true). No uses read_files, ls ni find. No pares hasta que la respuesta traiga done=true y la ruta de RESUMEN-EJECUTIVO.md.
```

### 4. Revisar findings detallados
```bash
ls /home/usuario/proyectos/nueva-app/.mvp-audit/findings/
cat /home/usuario/proyectos/nueva-app/.mvp-audit/findings/00-scan-review.md
```

---

## Notas Importantes

### ⚠️ gitleaks requiere git
Si usas `security-static-first` y ves "gitleaks: error" en `static/README.md`:
```bash
cd /home/usuario/proyectos/mi-app
git init
```

### ⚠️ Codebases grandes
Para proyectos con >100 archivos, considera:
- Usar `security-baseline` primero (más rápido)
- Luego `security-full` si baseline no encuentra issues críticos
- `security-static-first` para máxima cobertura (más lento)

### ⚠️ Archivos muy grandes
El sistema maneja automáticamente archivos grandes (>1MB) con `line_limit=40`.
No requiere configuración adicional.

---

## Troubleshooting

### "No module named 'mvp_memory'"
```bash
cd /path/to/MVP-code-review-full-context-control
source .venv/bin/activate
pip install -e .
```

### "MCP namespace not found"
Verifica configuración en:
- Cursor: `~/.cursor/mcp.json`
- Cline: `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- Continue: Ver [`docs/other-configs.md`](other-configs.md)

### Auditoría no termina
1. Anota el `project_id` de la respuesta
2. Usa el prompt de reanudación
3. Si persiste, verifica logs del MCP server

---

Más información: [`README.md`](../README.md) | [`docs/other-configs.md`](other-configs.md)
