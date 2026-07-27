#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
DATA_DIR="${MVP_MEMORY_DATA_DIR:-$HOME/.local/share/mvp-memory-context}"
exec python -m mvp_memory.api.main --data-dir "$DATA_DIR" --host 127.0.0.1 --port 8765 "$@"
