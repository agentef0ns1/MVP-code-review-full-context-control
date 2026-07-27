from __future__ import annotations

import json
from typing import Any

from mvp_memory.core.db import Database


class AuditService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def log(
        self,
        conn,
        *,
        actor: str,
        action: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        payload: dict | None = None,
        ip: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO audit_log (
                actor, actor_session, action, entity_type, entity_id, project_id, payload_json, ip
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor,
                session_id,
                action,
                entity_type,
                entity_id,
                project_id,
                json.dumps(payload or {}),
                ip,
            ),
        )
