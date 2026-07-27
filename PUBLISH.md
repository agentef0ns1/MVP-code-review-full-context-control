# Publicar / clonar limpio

Este repositorio está pensado para subirse sin artefactos locales.

## Qué **no** debe ir al remoto

| Elemento | Ubicación típica |
|----------|------------------|
| Entorno virtual | `.venv/` |
| Base SQLite / datos MCP | `data/`, `~/.local/share/mvp-memory-context/` |
| Token panel admin | `~/.config/mvp-memory-context/admin.token` |
| Caché tests | `.pytest_cache/`, `__pycache__/` |
| Salida de auditorías | `**/.mvp-audit/` en repos analizados |
| Secretos | `.env`, tokens en JSON de cliente |

Todo lo anterior está en `.gitignore`.

## Copia lista para GitHub (directorio hermano)

Desde el directorio padre del clon:

```bash
rsync -a --delete \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '*.egg-info/' \
  --exclude 'data/' \
  --exclude '*.db' \
  --exclude '.git/' \
  MVP-memory-context/ \
  MVP-code-analisys-full-context-control/

cd MVP-code-analisys-full-context-control
git init
git add -A
git status   # revisar: sin .venv, sin data/, sin tokens
```

Tras clonar en otra máquina: `./scripts/install.sh` crea `.venv` y, al arrancar la API, el token admin en el home del usuario (fuera del repo).

## Nombre del repo vs paquete Python

- **Repo sugerido:** `MVP-code-analisys-full-context-control`
- **Paquete pip / módulo:** `mvp-memory-context` (`mvp_memory`)
