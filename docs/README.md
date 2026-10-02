# Documentación MVP Memory Context

## Documentos Principales

- **[README.md](../README.md)** - Documentación principal del proyecto
- **[ejemplos-prompts.md](ejemplos-prompts.md)** - Prompts de ejemplo para auditorías
- **[other-configs.md](other-configs.md)** - Configuraciones avanzadas y clientes alternativos

## Guías Rápidas

### Para empezar
1. Lee el [README.md](../README.md) principal
2. Instala con `./scripts/install.sh`
3. Prueba con el Inspector: `./scripts/run-mcp-inspector.sh`
4. Copia un prompt de [ejemplos-prompts.md](ejemplos-prompts.md)

### Para usar con tu LLM local
Consulta [ejemplos-prompts.md](ejemplos-prompts.md) para prompts listos con:
- security-baseline (rápido)
- security-injection (inyecciones)
- js-console-api (APIs de consola)
- security-full (exhaustivo)
- security-static-first (con semgrep/gitleaks)

### Para configurar otros clientes
Ver [other-configs.md](other-configs.md) para:
- Cursor
- Continue
- SSE
- API web
