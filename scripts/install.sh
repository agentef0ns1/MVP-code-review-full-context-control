#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e ".[dev]"

DATA_DIR="${MVP_MEMORY_DATA_DIR:-$HOME/.local/share/mvp-memory-context}"
mkdir -p "$DATA_DIR"

echo ""
echo "Instalación completada."
echo "  venv: $ROOT/.venv"
echo "  data: $DATA_DIR"
echo ""
echo "Token admin (se crea al arrancar API): ~/.config/mvp-memory-context/admin.token"
echo ""
echo "MCP (Cursor / Cline):"
python3 - <<PY
import json
root = "$ROOT"
data = "$DATA_DIR"
print(json.dumps({
  "mcpServers": {
    "mvp-memory-context": {
      "command": f"{root}/.venv/bin/python",
      "args": ["-m", "mvp_memory.mcp_server", "--data-dir", data]
    }
  }
}, indent=2))
PY
