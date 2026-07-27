from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from mvp_memory.core.errors import MemoryError


class LockService:
    def acquire(
        self,
        conn,
        project_id: str,
        holder: str,
        ttl_seconds: int = 120,
    ) -> dict:
        ttl_seconds = min(max(ttl_seconds, 10), 3600)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl_seconds)
        existing = conn.execute(
            "SELECT * FROM project_locks WHERE project_id=?", (project_id,)
        ).fetchone()
        if existing:
            exp = datetime.fromisoformat(existing["expires_at"])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > now and existing["holder"] != holder:
                raise MemoryError(
                    "lock_held",
                    f"Lock held by {existing['holder']} until {existing['expires_at']}",
                )
        token = secrets.token_urlsafe(16)
        conn.execute(
            """
            INSERT INTO project_locks (project_id, holder, expires_at, token)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET holder=excluded.holder,
            expires_at=excluded.expires_at, token=excluded.token
            """,
            (project_id, holder, expires.replace(microsecond=0).isoformat(), token),
        )
        return {
            "project_id": project_id,
            "token": token,
            "expires_at": expires.replace(microsecond=0).isoformat(),
            "holder": holder,
        }

    def release(self, conn, project_id: str, token: str) -> dict:
        row = conn.execute(
            "SELECT token FROM project_locks WHERE project_id=?", (project_id,)
        ).fetchone()
        if not row or row["token"] != token:
            raise MemoryError("lock_invalid", "Invalid or missing lock token")
        conn.execute("DELETE FROM project_locks WHERE project_id=?", (project_id,))
        return {"project_id": project_id, "released": True}

    def validate_token(self, conn, project_id: str, token: str) -> None:
        row = conn.execute(
            "SELECT * FROM project_locks WHERE project_id=?", (project_id,)
        ).fetchone()
        if not row:
            return
        exp = datetime.fromisoformat(row["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            conn.execute("DELETE FROM project_locks WHERE project_id=?", (project_id,))
            return
        if row["token"] != token:
            raise MemoryError("lock_invalid", "Lock token required or invalid")

    def status(self, conn, project_id: str) -> dict:
        row = conn.execute(
            "SELECT * FROM project_locks WHERE project_id=?", (project_id,)
        ).fetchone()
        if not row:
            return {"locked": False}
        exp = datetime.fromisoformat(row["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            conn.execute("DELETE FROM project_locks WHERE project_id=?", (project_id,))
            return {"locked": False}
        return {
            "locked": True,
            "holder": row["holder"],
            "expires_at": row["expires_at"],
        }

    def break_glass(self, conn, project_id: str) -> dict:
        conn.execute("DELETE FROM project_locks WHERE project_id=?", (project_id,))
        return {"project_id": project_id, "released": True}
