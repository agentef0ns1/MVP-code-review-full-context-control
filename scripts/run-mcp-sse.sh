#!/usr/bin/env bash
# MCP SSE para Continue (stdio a veces hace timeout en el extension host).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${MVP_MEMORY_DATA_DIR:-$HOME/.local/share/mvp-memory-context}"
PORT="${MVP_MCP_SSE_PORT:-8766}"
exec "$ROOT/.venv/bin/mvp-memory-mcp" --data-dir "$DATA_DIR" --transport sse --host 127.0.0.1 --port "$PORT"
