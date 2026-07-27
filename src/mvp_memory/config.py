from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "mvp-memory-context"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "mvp-memory-context"


@dataclass
class Settings:
    data_dir: Path
    db_path: Path
    config_dir: Path
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    sqlcipher_enabled: bool = False
    semantic_search_enabled: bool = False

    @classmethod
    def from_args(
        cls,
        data_dir: str | Path | None = None,
        config_dir: str | Path | None = None,
        api_host: str | None = None,
        api_port: int | None = None,
        sqlcipher: bool = False,
        semantic: bool = False,
    ) -> Settings:
        dd = Path(data_dir).expanduser().resolve() if data_dir else DEFAULT_DATA_DIR
        cd = Path(config_dir).expanduser().resolve() if config_dir else DEFAULT_CONFIG_DIR
        env_dd = os.environ.get("MVP_MEMORY_DATA_DIR")
        if env_dd and not data_dir:
            dd = Path(env_dd).expanduser().resolve()
        return cls(
            data_dir=dd,
            db_path=dd / "memory.db",
            config_dir=cd,
            api_host=api_host or os.environ.get("MVP_MEMORY_API_HOST", "127.0.0.1"),
            api_port=api_port or int(os.environ.get("MVP_MEMORY_API_PORT", "8765")),
            sqlcipher_enabled=sqlcipher or os.environ.get("MVP_MEMORY_SQLCIPHER", "").lower() in ("1", "true", "yes"),
            semantic_search_enabled=semantic or os.environ.get("MVP_MEMORY_SEMANTIC", "").lower() in ("1", "true", "yes"),
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "exports").mkdir(exist_ok=True)

    def admin_token_path(self) -> Path:
        return self.config_dir / "admin.token"

    def get_or_create_admin_token(self) -> str:
        path = self.admin_token_path()
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
        token = secrets.token_urlsafe(32)
        path.write_text(token, encoding="utf-8")
        path.chmod(0o600)
        return token


def slugify_project_id(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return base[:48] or "project"


def project_id_from_workspace(workspace_path: str | Path) -> str:
    path = str(Path(workspace_path).expanduser().resolve())
    digest = hashlib.sha256(path.encode()).hexdigest()[:6]
    slug = slugify_project_id(Path(path).name)
    return f"{slug}-{digest}"


def content_hash(title: str, body: str, tags: list[str]) -> str:
    payload = json.dumps({"t": title, "b": body, "tags": tags}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def new_uuid() -> str:
    return str(uuid.uuid4())
