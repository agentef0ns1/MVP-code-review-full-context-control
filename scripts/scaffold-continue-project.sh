#!/usr/bin/env bash
# Copia plantillas Continue para un proyecto (memoria MCP, sin acoplar a campaña TFM).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPL="$ROOT/templates/continue"

if [[ $# -lt 2 ]]; then
  echo "Uso: $0 <workspace_absoluto> <project_id> [display_name]"
  echo "Ej:  $0 /home/user/mi-repo mi-repo-a1b2c3"
  exit 1
fi

WS="$(realpath "$1")"
PID="$2"
DN="${3:-$PID}"

mkdir -p "$WS/.continue/rules" "$WS/.continue/mcpServers"
cp "$TEMPL/mcpServers/mvp-memory-context.json" "$WS/.continue/mcpServers/"
cp "$TEMPL/rules/00-mvp-memory-estado.md" "$WS/.continue/rules/01-mvp-memory-estado.md"
cp "$TEMPL/rules/01-contexto-minimo.md" "$WS/.continue/rules/02-contexto-minimo.md"
cp "$TEMPL/rules/05-ollama-qwen-tool-xml.md" "$WS/.continue/rules/05-ollama-qwen-tool-xml.md"

RULE="$WS/.continue/rules/01-mvp-memory-estado.md"
python3 - <<PY
from pathlib import Path
p = Path("$RULE")
text = p.read_text(encoding="utf-8")
text = text.replace("<ID_ESTABLE>", "$PID")
text = text.replace("ruta absoluta de la raíz abierta en VS Code", "$WS")
p.write_text(text, encoding="utf-8")
PY

cat > "$WS/.continue/config.yaml" <<EOF
name: $DN
version: 1.0.0
schema: v1
# Modelos: perfil global ~/.continue/config.yaml (Main Config)
# MCP: .continue/mcpServers/mvp-memory-context.json — NO duplicar en Main Config
EOF

echo "OK: Continue scaffold en $WS"
echo "  project_id: $PID"
echo "  Abre VS Code en esa carpeta → Agent → activa rules → Tools mvp-memory-context Automatic"
echo "  MCP: Reset Cached Tools si cambiaste JSON"
