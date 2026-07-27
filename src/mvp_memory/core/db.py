from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from mvp_memory.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.settings.ensure_dirs()
            self._conn = sqlite3.connect(
                str(self.settings.db_path),
                check_same_thread=False,
                timeout=30.0,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=30000")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def migrate(self) -> None:
        here = Path(__file__).resolve()
        for candidate in (here.parents[3], here.parents[2], Path.cwd()):
            migrations_dir = candidate / "migrations"
            if migrations_dir.is_dir():
                break
        else:
            raise RuntimeError("migrations directory not found")
        conn = self.connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        applied = {
            row[0]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            version = int(sql_file.stem.split("_")[0])
            if version in applied:
                continue
            sql = sql_file.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)",
                (version,),
            )
        conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}
