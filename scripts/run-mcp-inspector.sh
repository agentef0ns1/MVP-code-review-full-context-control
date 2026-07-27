#!/usr/bin/env bash
# Arranca MCP Inspector (@modelcontextprotocol/inspector) contra mvp-memory-context.
# Requiere: Node.js/npm (npx). Abre UI en el navegador (puerto habitual 6274).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${MVP_MEMORY_DATA_DIR:-$HOME/.local/share/mvp-memory-context}"
PY="${ROOT}/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: no existe $PY — ejecuta scripts/install.sh" >&2
  exit 1
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "ERROR: npx no encontrado. Instala Node.js (nodejs npm)." >&2
  exit 1
fi

export MVP_MEMORY_DATA_DIR="$DATA_DIR"

echo "Inspector → MCP: mvp-memory-context"
echo "  data-dir: $DATA_DIR"
echo "  python:   $PY -m mvp_memory.mcp_server"
echo ""
echo "En Inspector: pestaña Prompts (audit-quickstart, audit-orchestration, audit-security-full)"
echo "             pestaña Tools (memory_audit_start, ...)"
echo ""

exec npx --yes @modelcontextprotocol/inspector@latest \
  "$PY" \
  -m mvp_memory.mcp_server \
  --data-dir "$DATA_DIR"
