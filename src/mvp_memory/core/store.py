from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from mvp_memory import SCHEMA_VERSION
from pathlib import Path

from mvp_memory.config import Settings, content_hash, new_uuid
from mvp_memory.core.audit import AuditService
from mvp_memory.core.db import Database, row_to_dict
from mvp_memory.core.locks import LockService
from mvp_memory.core.search import SearchService
from mvp_memory.core.semantic import SemanticSearchService
from mvp_memory.core.workspace_plan import WorkspacePlanService
from mvp_memory.core.audit_runner import run_audit
from mvp_memory.core.audit_session import AuditSessionService
from mvp_memory.audit_profiles_loader import (
    load_profile,
    list_profiles,
    list_prompt_catalog,
    render_audit_prompt,
    slug_from_path,
)
from mvp_memory.audit_findings import write_scan_index, record_finding, finalize_audit
from mvp_memory.core.static_analysis import run_static_tools

INITIAL_STATE_JSON = json.dumps(
    {
        "pendings": [],
        "conventions": [],
        "notes": "Proyecto inicializado; sin historial previo.",
    }
)

ENTRY_TYPES = frozenset(
    {"event", "decision", "pending", "error", "file_ref", "long_term", "init"}
)
PROJECT_STATUSES = frozenset({"active", "frozen", "archived"})


from mvp_memory.core.errors import MemoryError


class MemoryStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings)
        self.db.migrate()
        self.audit = AuditService(self.db)
        self.locks = LockService()
        self.search_engine = SearchService(self.db)
        self.semantic = SemanticSearchService(settings, self.db)
        self.workspace = WorkspacePlanService(settings, self.db)
        self.audit_session = AuditSessionService(settings, self.workspace)

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _parse_json(self, raw: str | None, default: Any) -> Any:
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    def _entry_dict(self, row) -> dict:
        d = row_to_dict(row) or {}
        d["tags"] = self._parse_json(d.pop("tags_json", "[]"), [])
        d["metadata"] = self._parse_json(d.pop("metadata_json", "{}"), {})
        d["frozen"] = bool(d.get("frozen"))
        d["human_only"] = bool(d.get("human_only"))
        return d

    def _touch_project(self, conn, project_id: str, session_id: str | None = None) -> None:
        now = self._now()
        if session_id:
            conn.execute(
                """
                UPDATE projects SET updated_at=?, last_accessed_at=?, last_agent_session_id=?
                WHERE id=?
                """,
                (now, now, session_id, project_id),
            )
        else:
            conn.execute(
                "UPDATE projects SET updated_at=?, last_accessed_at=? WHERE id=?",
                (now, now, project_id),
            )

    def _next_sequence(self, conn, project_id: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS n FROM memory_entries WHERE project_id=?",
            (project_id,),
        ).fetchone()
        return int(row["n"])

    def _index_fts(self, conn, entry: dict) -> None:
        conn.execute("DELETE FROM fts_memory WHERE entry_id=?", (entry["id"],))
        conn.execute(
            """
            INSERT INTO fts_memory (entry_id, project_id, title, body, tags)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entry["id"],
                entry["project_id"],
                entry.get("title") or "",
                entry.get("body") or "",
                " ".join(entry.get("tags") or []),
            ),
        )

    def _require_writable_entry(self, entry: dict, actor: str) -> None:
        if entry.get("frozen"):
            raise MemoryError("readonly", "Entry is frozen (read-only)")
        if entry.get("human_only") and actor == "agent":
            raise MemoryError("human_only", "Entry is human-only")

    def _require_active_project(self, conn, project_id: str, actor: str) -> dict:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            raise MemoryError("not_found", f"Project {project_id} not found")
        proj = row_to_dict(row)
        if proj["status"] == "frozen" and actor == "agent":
            raise MemoryError("frozen", "Project is frozen for agent writes")
        return proj

    def list_projects(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        conn = self.db.connect()
        limit = min(max(limit, 1), 200)
        offset = max(offset, 0)
        if status and status not in PROJECT_STATUSES:
            raise MemoryError("invalid", f"Invalid status: {status}")
        if status:
            rows = conn.execute(
                """
                SELECT * FROM projects WHERE status=? ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (status, limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM projects WHERE status=?", (status,)
            ).fetchone()["c"]
        else:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]
        return {
            "schema_version": SCHEMA_VERSION,
            "total": total,
            "projects": [row_to_dict(r) for r in rows],
        }

    def create_project(
        self,
        project_id: str,
        display_name: str | None = None,
        workspace_path: str | None = None,
        actor: str = "agent",
        session_id: str | None = None,
    ) -> dict:
        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM projects WHERE id=?", (project_id,)
            ).fetchone()
            if existing:
                raise MemoryError("exists", f"Project {project_id} already exists")
            now = self._now()
            conn.execute(
                """
                INSERT INTO projects (id, display_name, workspace_path, created_at, updated_at, last_accessed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    display_name or project_id,
                    workspace_path,
                    now,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO project_state (project_id, version, summary, checkpoint, state_json, updated_at, updated_by)
                VALUES (?, 1, '', '', ?, ?, 'system')
                """,
                (project_id, INITIAL_STATE_JSON, now),
            )
            init_entry = self._insert_entry_unlocked(
                conn,
                project_id=project_id,
                entry_type="init",
                title="Project initialized",
                body="Auto or explicit project creation.",
                tags=["init"],
                metadata={},
                scope="persistent",
                actor=actor,
                session_id=session_id,
            )
            self.audit.log(
                conn,
                actor=actor,
                action="project.created",
                entity_type="project",
                entity_id=project_id,
                project_id=project_id,
                session_id=session_id,
            )
        return {"schema_version": SCHEMA_VERSION, "project_id": project_id, "init_entry_id": init_entry["id"]}

    def initialize_if_missing(
        self,
        project_id: str,
        display_name: str | None = None,
        workspace_path: str | None = None,
        actor: str = "agent",
        session_id: str | None = None,
    ) -> tuple[dict, bool]:
        conn = self.db.connect()
        row = conn.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
        if row:
            return self.get_project_row(project_id), False
        try:
            self.create_project(project_id, display_name, workspace_path, actor, session_id)
        except MemoryError as e:
            if e.code != "exists":
                raise
        return self.get_project_row(project_id), True

    def get_project_row(self, project_id: str) -> dict:
        conn = self.db.connect()
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            raise MemoryError("not_found", f"Project {project_id} not found")
        return row_to_dict(row)

    def get_state(
        self,
        project_id: str,
        auto_create: bool = True,
        include_sections: list[str] | None = None,
        compact: bool = False,
        actor: str = "agent",
        session_id: str | None = None,
    ) -> dict:
        created = False
        if auto_create:
            _, created = self.initialize_if_missing(project_id, actor=actor, session_id=session_id)
        else:
            self.get_project_row(project_id)

        if compact:
            sections = include_sections or ["summary", "stats", "decisions", "pendings"]
        else:
            sections = include_sections or [
                "metadata",
                "summary",
                "recent_events",
                "decisions",
                "pendings",
                "errors",
                "files",
                "long_term",
                "stats",
            ]
        conn = self.db.connect()
        with self.db.transaction() as conn:
            self._touch_project(conn, project_id, session_id)
            metadata = self.get_project_row(project_id)
            st = conn.execute(
                "SELECT * FROM project_state WHERE project_id=?", (project_id,)
            ).fetchone()
            state_row = row_to_dict(st) or {}
            state_json = self._parse_json(state_row.get("state_json"), {})

        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "initialized": created,
            "compact": compact,
        }
        if compact:
            result["metadata"] = {
                "id": metadata.get("id"),
                "status": metadata.get("status"),
                "workspace_path": metadata.get("workspace_path"),
            }
        elif "metadata" in sections:
            result["metadata"] = metadata
        if "summary" in sections:
            result["summary"] = state_row.get("summary", "")
            result["checkpoint"] = state_row.get("checkpoint", "")
            if compact:
                result["state_json"] = {
                    k: state_json[k]
                    for k in ("total_iters_target", "doc_root", "next_slug", "next_iter")
                    if k in state_json
                }
            else:
                result["state_json"] = state_json
        if "stats" in sections:
            result["stats"] = self._project_stats(conn, project_id)

        slim_limits = {"decisions": 5, "pendings": 8, "recent_events": 3} if compact else {}
        type_map = {
            "recent_events": ("event", 15),
            "decisions": ("decision", 20),
            "pendings": ("pending", 30),
            "errors": ("error", 20),
            "files": ("file_ref", 30),
            "long_term": ("long_term", 20),
        }
        for key, (etype, lim) in type_map.items():
            if key in sections:
                cap = slim_limits.get(key, lim)
                entries = self._list_entries_by_type(conn, project_id, etype, cap)
                if compact:
                    result[key] = self._slim_entries(entries)
                else:
                    result[key] = entries

        if compact:
            result["hint"] = (
                "Detalle en disco (indice.md) o memory_search / memory_get_entry; "
                "no uses get_state compact=false salvo depuración."
            )

        return result

    def get_checkpoint(
        self,
        project_id: str,
        auto_create: bool = False,
        actor: str = "agent",
        session_id: str | None = None,
    ) -> dict:
        """Minimal state for agent rehydration (~small JSON)."""
        return self.get_state(
            project_id,
            auto_create=auto_create,
            compact=True,
            actor=actor,
            session_id=session_id,
        )

    def _slim_entries(self, entries: list[dict]) -> list[dict]:
        return [
            {
                "id": e["id"],
                "title": e.get("title", ""),
                "sequence": e.get("sequence"),
                "entry_type": e.get("entry_type"),
            }
            for e in entries
        ]

    def _project_stats(self, conn, project_id: str) -> dict:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c,
                   MAX(updated_at) AS last_change
            FROM memory_entries
            WHERE project_id=? AND deleted_at IS NULL
            """,
            (project_id,),
        ).fetchone()
        proj = conn.execute(
            "SELECT memory_size_bytes, last_accessed_at FROM projects WHERE id=?",
            (project_id,),
        ).fetchone()
        return {
            "entry_count": row["c"],
            "last_change": row["last_change"],
            "memory_size_bytes": proj["memory_size_bytes"] if proj else 0,
            "last_accessed_at": proj["last_accessed_at"] if proj else None,
        }

    def _list_entries_by_type(
        self, conn, project_id: str, entry_type: str, limit: int
    ) -> list[dict]:
        if entry_type == "pending":
            rows = conn.execute(
                """
                SELECT * FROM memory_entries
                WHERE project_id=? AND entry_type='pending' AND deleted_at IS NULL
                ORDER BY sequence DESC LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM memory_entries
                WHERE project_id=? AND entry_type=? AND deleted_at IS NULL
                ORDER BY sequence DESC LIMIT ?
                """,
                (project_id, entry_type, limit),
            ).fetchall()
        return [self._entry_dict(r) for r in rows]

    def _insert_entry_unlocked(
        self,
        conn,
        *,
        project_id: str,
        entry_type: str,
        title: str,
        body: str,
        tags: list[str] | None,
        metadata: dict | None,
        scope: str,
        actor: str,
        session_id: str | None,
        supersedes_id: str | None = None,
        human_only: bool = False,
    ) -> dict:
        if entry_type not in ENTRY_TYPES:
            raise MemoryError("invalid", f"Invalid entry_type: {entry_type}")
        tags = tags or []
        metadata = metadata or {}
        eid = new_uuid()
        seq = self._next_sequence(conn, project_id)
        now = self._now()
        ch = content_hash(title, body, tags)
        conn.execute(
            """
            INSERT INTO memory_entries (
                id, project_id, entry_type, scope, title, body, tags_json, metadata_json,
                sequence, created_at, created_by, session_id, updated_at, updated_by,
                content_hash, supersedes_id, human_only
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                project_id,
                entry_type,
                scope,
                title,
                body,
                json.dumps(tags),
                json.dumps(metadata),
                seq,
                now,
                actor,
                session_id,
                now,
                actor,
                ch,
                supersedes_id,
                1 if human_only else 0,
            ),
        )
        entry = self._entry_dict(
            conn.execute("SELECT * FROM memory_entries WHERE id=?", (eid,)).fetchone()
        )
        self._index_fts(conn, entry)
        self.semantic.index_entry(entry)
        size = len(title) + len(body) + len(json.dumps(tags)) + len(json.dumps(metadata))
        conn.execute(
            """
            UPDATE projects SET memory_size_bytes = memory_size_bytes + ?, updated_at=?
            WHERE id=?
            """,
            (size, now, project_id),
        )
        conn.execute(
            """
            INSERT INTO memory_entry_versions (entry_id, version, title, body, tags_json, metadata_json, changed_by, change_reason)
            VALUES (?, 1, ?, ?, ?, ?, ?, 'created')
            """,
            (eid, title, body, json.dumps(tags), json.dumps(metadata), actor),
        )
        return entry

    def append_entry(
        self,
        project_id: str,
        entry_type: str,
        title: str,
        body: str,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        scope: str = "working",
        actor: str = "agent",
        session_id: str | None = None,
        supersedes_id: str | None = None,
        lock_token: str | None = None,
    ) -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, actor)
            if actor == "agent" and lock_token:
                self.locks.validate_token(conn, project_id, lock_token)
            entry = self._insert_entry_unlocked(
                conn,
                project_id=project_id,
                entry_type=entry_type,
                title=title,
                body=body,
                tags=tags,
                metadata=metadata,
                scope=scope,
                actor=actor,
                session_id=session_id,
                supersedes_id=supersedes_id,
            )
            self.audit.log(
                conn,
                actor=actor,
                action=f"entry.{entry_type}.created",
                entity_type="memory_entry",
                entity_id=entry["id"],
                project_id=project_id,
                session_id=session_id,
                payload={"title": title},
            )
        return {"schema_version": SCHEMA_VERSION, "entry": entry}

    def update_summary(
        self,
        project_id: str,
        summary: str | None = None,
        checkpoint: str | None = None,
        state_patch: dict | None = None,
        actor: str = "agent",
        session_id: str | None = None,
        lock_token: str | None = None,
    ) -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, actor)
            if actor == "agent" and lock_token:
                self.locks.validate_token(conn, project_id, lock_token)
            row = conn.execute(
                "SELECT * FROM project_state WHERE project_id=?", (project_id,)
            ).fetchone()
            if not row:
                raise MemoryError("not_found", "Project state missing")
            state_json = self._parse_json(row["state_json"], {})
            if state_patch:
                state_json.update(state_patch)
            new_summary = summary if summary is not None else row["summary"]
            new_checkpoint = checkpoint if checkpoint is not None else row["checkpoint"]
            new_version = int(row["version"]) + 1
            now = self._now()
            conn.execute(
                """
                UPDATE project_state SET version=?, summary=?, checkpoint=?, state_json=?,
                updated_at=?, updated_by=? WHERE project_id=?
                """,
                (
                    new_version,
                    new_summary,
                    new_checkpoint,
                    json.dumps(state_json),
                    now,
                    actor,
                    project_id,
                ),
            )
            self.audit.log(
                conn,
                actor=actor,
                action="project_state.updated",
                entity_type="project_state",
                entity_id=project_id,
                project_id=project_id,
                session_id=session_id,
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "version": new_version,
            "summary": new_summary,
            "checkpoint": new_checkpoint,
            "state_json": state_json,
        }

    def get_entry(self, entry_id: str) -> dict:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT * FROM memory_entries WHERE id=? AND deleted_at IS NULL",
            (entry_id,),
        ).fetchone()
        if not row:
            raise MemoryError("not_found", f"Entry {entry_id} not found")
        return {"schema_version": SCHEMA_VERSION, "entry": self._entry_dict(row)}

    def update_entry(
        self,
        entry_id: str,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        reason: str = "",
        actor: str = "agent",
        session_id: str | None = None,
        human_only: bool | None = None,
    ) -> dict:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM memory_entries WHERE id=? AND deleted_at IS NULL",
                (entry_id,),
            ).fetchone()
            if not row:
                raise MemoryError("not_found", f"Entry {entry_id} not found")
            entry = self._entry_dict(row)
            self._require_writable_entry(entry, actor)
            self._require_active_project(conn, entry["project_id"], actor)
            new_title = title if title is not None else entry["title"]
            new_body = body if body is not None else entry["body"]
            new_tags = tags if tags is not None else entry["tags"]
            new_meta = metadata if metadata is not None else entry["metadata"]
            ver_row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS v FROM memory_entry_versions WHERE entry_id=?",
                (entry_id,),
            ).fetchone()
            new_ver = int(ver_row["v"])
            now = self._now()
            ho = entry["human_only"] if human_only is None else human_only
            conn.execute(
                """
                UPDATE memory_entries SET title=?, body=?, tags_json=?, metadata_json=?,
                updated_at=?, updated_by=?, content_hash=?, human_only=? WHERE id=?
                """,
                (
                    new_title,
                    new_body,
                    json.dumps(new_tags),
                    json.dumps(new_meta),
                    now,
                    actor,
                    content_hash(new_title, new_body, new_tags),
                    1 if ho else 0,
                    entry_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO memory_entry_versions (
                    entry_id, version, title, body, tags_json, metadata_json, changed_by, change_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    new_ver,
                    new_title,
                    new_body,
                    json.dumps(new_tags),
                    json.dumps(new_meta),
                    actor,
                    reason or "updated",
                ),
            )
            updated = self._entry_dict(
                conn.execute("SELECT * FROM memory_entries WHERE id=?", (entry_id,)).fetchone()
            )
            self._index_fts(conn, updated)
            self.semantic.index_entry(updated)
            self.audit.log(
                conn,
                actor=actor,
                action="entry.updated",
                entity_type="memory_entry",
                entity_id=entry_id,
                project_id=entry["project_id"],
                session_id=session_id,
                payload={"reason": reason, "version": new_ver},
            )
        return {"schema_version": SCHEMA_VERSION, "entry": updated, "version": new_ver}

    def delete_entry(
        self,
        entry_id: str,
        reason: str,
        confirm: bool,
        actor: str = "agent",
        session_id: str | None = None,
    ) -> dict:
        if not confirm:
            raise MemoryError("confirm_required", "Set confirm=true for soft delete")
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM memory_entries WHERE id=? AND deleted_at IS NULL",
                (entry_id,),
            ).fetchone()
            if not row:
                raise MemoryError("not_found", f"Entry {entry_id} not found")
            entry = self._entry_dict(row)
            if entry.get("frozen"):
                raise MemoryError("readonly", "Cannot delete frozen entry")
            now = self._now()
            conn.execute(
                "UPDATE memory_entries SET deleted_at=?, updated_at=?, updated_by=? WHERE id=?",
                (now, now, actor, entry_id),
            )
            conn.execute("DELETE FROM fts_memory WHERE entry_id=?", (entry_id,))
            conn.execute("DELETE FROM entry_embeddings WHERE entry_id=?", (entry_id,))
            self.audit.log(
                conn,
                actor=actor,
                action="entry.deleted",
                entity_type="memory_entry",
                entity_id=entry_id,
                project_id=entry["project_id"],
                session_id=session_id,
                payload={"reason": reason},
            )
        return {"schema_version": SCHEMA_VERSION, "entry_id": entry_id, "deleted": True}

    def purge_entry(
        self,
        entry_id: str,
        confirm_token: str,
        actor: str = "human",
        ip: str | None = None,
    ) -> dict:
        expected = self.settings.get_or_create_admin_token()
        if confirm_token != expected:
            raise MemoryError("forbidden", "Invalid confirm_token for purge")
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT project_id FROM memory_entries WHERE id=?", (entry_id,)
            ).fetchone()
            if not row:
                raise MemoryError("not_found", f"Entry {entry_id} not found")
            project_id = row["project_id"]
            conn.execute("DELETE FROM memory_entry_versions WHERE entry_id=?", (entry_id,))
            conn.execute("DELETE FROM memory_entries WHERE id=?", (entry_id,))
            self.audit.log(
                conn,
                actor=actor,
                action="entry.purged",
                entity_type="memory_entry",
                entity_id=entry_id,
                project_id=project_id,
                ip=ip,
            )
        return {"schema_version": SCHEMA_VERSION, "entry_id": entry_id, "purged": True}

    def resolve_pending(
        self,
        entry_id: str,
        resolution: str,
        actor: str = "agent",
        session_id: str | None = None,
    ) -> dict:
        meta_patch = {"resolved": True, "resolution": resolution, "resolved_at": self._now()}
        entry = self.get_entry(entry_id)["entry"]
        if entry["entry_type"] != "pending":
            raise MemoryError("invalid", "Entry is not a pending item")
        merged = {**entry["metadata"], **meta_patch}
        return self.update_entry(
            entry_id,
            body=f"{entry['body']}\n\nResolution: {resolution}",
            metadata=merged,
            reason="pending resolved",
            actor=actor,
            session_id=session_id,
        )

    def search(
        self,
        project_id: str,
        query: str,
        types: list[str] | None = None,
        tags: list[str] | None = None,
        since: str | None = None,
        limit: int = 20,
        semantic: bool | None = None,
    ) -> dict:
        self.get_project_row(project_id)
        use_semantic = semantic if semantic is not None else self.settings.semantic_search_enabled
        fts_hits = self.search_engine.search(project_id, query, types, tags, since, limit)
        if use_semantic and query.strip():
            sem_hits = self.semantic.search(project_id, query, limit)
            seen = {h["entry_id"] for h in fts_hits}
            for h in sem_hits:
                if h["entry_id"] not in seen:
                    fts_hits.append(h)
                    seen.add(h["entry_id"])
        conn = self.db.connect()
        entries = []
        for hit in fts_hits[:limit]:
            row = conn.execute(
                "SELECT * FROM memory_entries WHERE id=? AND deleted_at IS NULL",
                (hit["entry_id"],),
            ).fetchone()
            if row:
                e = self._entry_dict(row)
                e["score"] = hit.get("score", 0)
                entries.append(e)
        return {"schema_version": SCHEMA_VERSION, "query": query, "count": len(entries), "entries": entries}

    def export_project(self, project_id: str, fmt: str = "json") -> dict:
        self.get_project_row(project_id)
        conn = self.db.connect()
        proj = self.get_project_row(project_id)
        state = row_to_dict(
            conn.execute(
                "SELECT * FROM project_state WHERE project_id=?", (project_id,)
            ).fetchone()
        )
        entries = [
            self._entry_dict(r)
            for r in conn.execute(
                """
                SELECT * FROM memory_entries WHERE project_id=? ORDER BY sequence
                """,
                (project_id,),
            ).fetchall()
        ]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "exported_at": self._now(),
            "project": proj,
            "project_state": state,
            "entries": entries,
        }
        if fmt == "ndjson":
            lines = [json.dumps({"type": "project", "data": proj})]
            lines.append(json.dumps({"type": "project_state", "data": state}))
            for e in entries:
                lines.append(json.dumps({"type": "entry", "data": e}))
            text = "\n".join(lines)
        else:
            text = json.dumps(payload, indent=2, ensure_ascii=False)
        export_path = self.settings.data_dir / "exports" / f"{project_id}-{int(datetime.now().timestamp())}.json"
        export_path.write_text(text, encoding="utf-8")
        return {"schema_version": SCHEMA_VERSION, "path": str(export_path), "format": fmt, "entry_count": len(entries)}

    def import_project(
        self,
        data: dict | str,
        mode: str = "merge",
        confirm_overwrite: bool = False,
        actor: str = "human",
        ip: str | None = None,
    ) -> dict:
        if isinstance(data, str):
            payload = json.loads(data)
        else:
            payload = data
        project = payload.get("project") or {}
        project_id = project.get("id")
        if not project_id:
            raise MemoryError("invalid", "Import missing project.id")
        exists = False
        try:
            self.get_project_row(project_id)
            exists = True
        except MemoryError:
            pass
        if exists and mode == "replace" and not confirm_overwrite:
            raise MemoryError("confirm_required", "confirm_overwrite required for replace mode")
        with self.db.transaction() as conn:
            if exists and mode == "replace":
                conn.execute("DELETE FROM memory_entries WHERE project_id=?", (project_id,))
                conn.execute("DELETE FROM project_state WHERE project_id=?", (project_id,))
                conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
                conn.execute("DELETE FROM fts_memory WHERE project_id=?", (project_id,))
            if not exists or mode == "replace":
                conn.execute(
                    """
                    INSERT OR REPLACE INTO projects (
                        id, display_name, workspace_path, created_at, updated_at, status, memory_size_bytes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        project.get("display_name"),
                        project.get("workspace_path"),
                        project.get("created_at") or self._now(),
                        self._now(),
                        project.get("status") or "active",
                        project.get("memory_size_bytes") or 0,
                    ),
                )
            ps = payload.get("project_state") or {}
            conn.execute(
                """
                INSERT OR REPLACE INTO project_state (
                    project_id, version, summary, checkpoint, state_json, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    ps.get("version") or 1,
                    ps.get("summary") or "",
                    ps.get("checkpoint") or "",
                    ps.get("state_json") if isinstance(ps.get("state_json"), str) else json.dumps(ps.get("state_json") or {}),
                    self._now(),
                    actor,
                ),
            )
            imported = 0
            for raw in payload.get("entries") or []:
                eid = raw.get("id") or new_uuid()
                existing_e = conn.execute(
                    "SELECT id FROM memory_entries WHERE id=?", (eid,)
                ).fetchone()
                if existing_e and mode == "merge":
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_entries (
                        id, project_id, entry_type, scope, title, body, tags_json, metadata_json,
                        sequence, created_at, created_by, updated_at, updated_by, content_hash,
                        frozen, human_only, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        eid,
                        project_id,
                        raw.get("entry_type", "event"),
                        raw.get("scope", "working"),
                        raw.get("title", ""),
                        raw.get("body", ""),
                        json.dumps(raw.get("tags") or []),
                        json.dumps(raw.get("metadata") or {}),
                        raw.get("sequence") or self._next_sequence(conn, project_id),
                        raw.get("created_at") or self._now(),
                        raw.get("created_by") or actor,
                        raw.get("updated_at") or self._now(),
                        raw.get("updated_by") or actor,
                        raw.get("content_hash") or content_hash(raw.get("title", ""), raw.get("body", ""), raw.get("tags") or []),
                        1 if raw.get("frozen") else 0,
                        1 if raw.get("human_only") else 0,
                        raw.get("deleted_at"),
                    ),
                )
                entry = self._entry_dict(
                    conn.execute("SELECT * FROM memory_entries WHERE id=?", (eid,)).fetchone()
                )
                if not entry.get("deleted_at"):
                    self._index_fts(conn, entry)
                imported += 1
            self.audit.log(
                conn,
                actor=actor,
                action="project.imported",
                entity_type="project",
                entity_id=project_id,
                project_id=project_id,
                ip=ip,
                payload={"mode": mode, "imported_entries": imported},
            )
        return {"schema_version": SCHEMA_VERSION, "project_id": project_id, "imported_entries": imported}

    def freeze_project(self, project_id: str, reason: str, actor: str = "human") -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, "human")
            conn.execute(
                "UPDATE projects SET status='frozen', updated_at=? WHERE id=?",
                (self._now(), project_id),
            )
            self.audit.log(
                conn,
                actor=actor,
                action="project.frozen",
                entity_type="project",
                entity_id=project_id,
                project_id=project_id,
                payload={"reason": reason},
            )
        return {"schema_version": SCHEMA_VERSION, "project_id": project_id, "status": "frozen"}

    def reset_project(self, project_id: str, wipe: bool, confirm: bool, actor: str = "human") -> dict:
        if not confirm:
            raise MemoryError("confirm_required", "confirm=true required")
        with self.db.transaction() as conn:
            if wipe:
                conn.execute("DELETE FROM memory_entry_versions WHERE entry_id IN (SELECT id FROM memory_entries WHERE project_id=?)", (project_id,))
                conn.execute("DELETE FROM memory_entries WHERE project_id=?", (project_id,))
                conn.execute("DELETE FROM fts_memory WHERE project_id=?", (project_id,))
                conn.execute("DELETE FROM entry_embeddings WHERE project_id=?", (project_id,))
                conn.execute("DELETE FROM project_locks WHERE project_id=?", (project_id,))
                now = self._now()
                conn.execute(
                    """
                    UPDATE project_state SET version=1, summary='', checkpoint='', state_json=?,
                    updated_at=?, updated_by=? WHERE project_id=?
                    """,
                    (INITIAL_STATE_JSON, now, actor, project_id),
                )
                conn.execute(
                    "UPDATE projects SET memory_size_bytes=0, updated_at=?, status='active' WHERE id=?",
                    (now, project_id),
                )
                self._insert_entry_unlocked(
                    conn,
                    project_id=project_id,
                    entry_type="init",
                    title="Project reset",
                    body=f"Wipe reset by {actor}",
                    tags=["reset"],
                    metadata={"wipe": True},
                    scope="persistent",
                    actor=actor,
                    session_id=None,
                )
                action = "project.wiped"
            else:
                conn.execute(
                    "UPDATE projects SET status='archived', updated_at=? WHERE id=?",
                    (self._now(), project_id),
                )
                action = "project.archived"
            self.audit.log(
                conn,
                actor=actor,
                action=action,
                entity_type="project",
                entity_id=project_id,
                project_id=project_id,
            )
        return {"schema_version": SCHEMA_VERSION, "project_id": project_id, "wipe": wipe}

    def list_audit(
        self,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        conn = self.db.connect()
        limit = min(max(limit, 1), 500)
        if project_id:
            rows = conn.execute(
                """
                SELECT * FROM audit_log WHERE project_id=? ORDER BY id DESC LIMIT ? OFFSET ?
                """,
                (project_id, limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM audit_log WHERE project_id=?", (project_id,)
            ).fetchone()["c"]
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()["c"]
        items = []
        for r in rows:
            d = row_to_dict(r)
            d["payload"] = self._parse_json(d.pop("payload_json", "{}"), {})
            items.append(d)
        return {"schema_version": SCHEMA_VERSION, "total": total, "items": items}

    def entry_versions(self, entry_id: str) -> dict:
        conn = self.db.connect()
        rows = conn.execute(
            """
            SELECT * FROM memory_entry_versions WHERE entry_id=? ORDER BY version
            """,
            (entry_id,),
        ).fetchall()
        return {
            "schema_version": SCHEMA_VERSION,
            "entry_id": entry_id,
            "versions": [row_to_dict(r) for r in rows],
        }

    def lock_status(self, project_id: str) -> dict:
        conn = self.db.connect()
        return {"schema_version": SCHEMA_VERSION, **self.locks.status(conn, project_id)}

    def workspace_plan(
        self,
        project_id: str,
        *,
        profile: str = "security_code",
        reset: bool = False,
        workspace_path: str | None = None,
        auto_create: bool = False,
        actor: str = "agent",
        session_id: str | None = None,
    ) -> dict:
        with self.db.transaction() as conn:
            if auto_create:
                self.initialize_if_missing(
                    project_id,
                    workspace_path=workspace_path,
                    actor=actor,
                    session_id=session_id,
                )
            else:
                self._require_active_project(conn, project_id, actor)
            if workspace_path:
                conn.execute(
                    "UPDATE projects SET workspace_path=?, updated_at=? WHERE id=?",
                    (str(Path(workspace_path).expanduser().resolve()), self._now(), project_id),
                )
            self._touch_project(conn, project_id, session_id)
            result = self.workspace.plan(
                conn, project_id, profile=profile, reset=reset
            )
        return {"schema_version": SCHEMA_VERSION, **result}

    def workspace_next_unit(self, project_id: str, actor: str = "agent") -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, actor)
            result = self.workspace.next_unit(conn, project_id)
        return {"schema_version": SCHEMA_VERSION, **result}

    def workspace_read(
        self,
        project_id: str,
        rel_path: str,
        *,
        line_offset: int = 1,
        line_limit: int = 120,
        byte_offset: int = 0,
        byte_limit: int = 0,
        max_bytes: int = 48_000,
        actor: str = "agent",
    ) -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, actor)
            result = self.workspace.read_bounded(
                conn,
                project_id,
                rel_path,
                line_offset=line_offset,
                line_limit=line_limit,
                byte_offset=byte_offset,
                byte_limit=byte_limit,
                max_bytes=max_bytes,
            )
        return {"schema_version": SCHEMA_VERSION, **result}

    def workspace_complete_unit(
        self,
        project_id: str,
        unit_id: str,
        *,
        skip: bool = False,
        actor: str = "agent",
        session_id: str | None = None,
    ) -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, actor)
            self._touch_project(conn, project_id, session_id)
            result = self.workspace.complete_unit(
                conn, project_id, unit_id, skip=skip
            )
        return {"schema_version": SCHEMA_VERSION, **result}

    def workspace_scan_patterns(
        self,
        project_id: str,
        pattern: str,
        *,
        rel_path: str | None = None,
        max_count: int = 15,
        actor: str = "agent",
    ) -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, actor)
            result = self.workspace.scan_pattern(
                conn,
                project_id,
                pattern,
                rel_path=rel_path,
                max_count=max_count,
            )
        return {"schema_version": SCHEMA_VERSION, **result}

    def audit_start(
        self,
        target_directory: str,
        *,
        profile_id: str = "security-baseline",
        output_dir: str | None = None,
        display_name: str | None = None,
        reset: bool = True,
        actor: str = "agent",
        session_id: str | None = None,
    ) -> dict:
        target = Path(target_directory).expanduser().resolve()
        if not target.is_dir():
            raise MemoryError("not_found", f"Directorio no encontrado: {target}")

        project_id = slug_from_path(target)
        profile = load_profile(profile_id)
        out_rel = (output_dir or profile.get("output_dir_default") or ".mvp-audit").strip(
            "/\\"
        )
        out_path = (target / out_rel).resolve()

        conn_check = self.db.connect()
        if not conn_check.execute(
            "SELECT id FROM projects WHERE id=?", (project_id,)
        ).fetchone():
            self.create_project(
                project_id,
                display_name or target.name,
                str(target),
                actor,
                session_id,
            )
        else:
            with self.db.transaction() as conn:
                conn.execute(
                    """
                    UPDATE projects SET workspace_path=?, display_name=COALESCE(?, display_name),
                    updated_at=? WHERE id=?
                    """,
                    (str(target), display_name, self._now(), project_id),
                )

        scan_index = ""
        static_results: list[dict] = []
        with self.db.transaction() as conn:
            self._touch_project(conn, project_id, session_id)
            self.audit_session.scaffold_output(out_path, profile)
            plan_result = self.workspace.plan(
                conn, project_id, profile=profile_id, reset=reset
            )
            scans = self.audit_session.run_profile_scans(
                conn, project_id, profile, out_path / "scans"
            )
            scan_index = write_scan_index(out_path, scans)
            static_results = []
            if profile.get("static_tools"):
                static_results = run_static_tools(
                    target, out_path, profile["static_tools"]
                )
            config = {
                "profile_id": profile_id,
                "output_rel_dir": out_rel,
                "scans": scans,
                "scan_index": scan_index,
                "static_tools": static_results,
            }
            conn.execute(
                """
                INSERT INTO audit_sessions (project_id, profile_id, output_rel_dir, config_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    profile_id=excluded.profile_id,
                    output_rel_dir=excluded.output_rel_dir,
                    config_json=excluded.config_json,
                    updated_at=excluded.updated_at
                """,
                (project_id, profile_id, out_rel, json.dumps(config), self._now()),
            )

        self.append_entry(
            project_id,
            "decision",
            f"Auditoría perfil {profile_id}",
            f"Target: {target}\nOutput: {out_path}\nPerfil: {profile_id}",
            tags=["audit", profile_id],
            actor=actor,
            session_id=session_id,
        )
        pending_ids: list[str] = []
        for t in profile.get("tasks") or []:
            pe = self.append_entry(
                project_id,
                "pending",
                t["title"],
                f"Entregable: {out_rel}/{t['deliverable']}\nrequire_poc={t.get('require_poc', False)}",
                tags=["audit-task", t["id"]],
                metadata={"task_id": t["id"], "deliverable": t["deliverable"]},
                actor=actor,
                session_id=session_id,
            )
            pending_ids.append(pe["entry"]["id"])

        ctx = {
            "project_id": project_id,
            "workspace_path": str(target),
            "output_dir": str(out_path),
            "findings_dir": str(out_path / "findings"),
            "poc_dir": str(out_path / "poc"),
            "scans_dir": str(out_path / "scans"),
        }
        session_prompt = render_audit_prompt(profile, ctx)
        self.update_summary(
            project_id,
            summary=f"Auditoría {profile_id} en {out_rel}.",
            checkpoint=f"audit:start:{profile_id}",
            actor=actor,
            session_id=session_id,
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "workspace_path": str(target),
            "output_dir": str(out_path),
            "output_rel_dir": out_rel,
            "profile_id": profile_id,
            "profile_title": profile.get("title"),
            "unit_count": plan_result.get("unit_count"),
            "next_unit": plan_result.get("next_unit"),
            "scans": scans,
            "scan_index": scan_index,
            "static_tools": static_results,
            "search_count": len(profile.get("searches") or []),
            "pending_task_ids": pending_ids,
            "session_prompt": session_prompt,
            "next_tool": "memory_audit_next_step",
            "disk_required": (
                "Usa memory_audit_record_finding por cada hallazgo; "
                "memory_audit_finalize al cerrar. No basta el chat."
            ),
        }

    def audit_record_finding(
        self,
        project_id: str,
        severity: str,
        title: str,
        *,
        description: str = "",
        cwe: str | None = None,
        file_path: str | None = None,
        line: int | None = None,
        poc_markdown: str = "",
        evidence: str = "",
        actor: str = "agent",
        session_id: str | None = None,
    ) -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, actor)
            _root, out, _cfg = self.audit_session._output_root(conn, project_id)
        rec = record_finding(
            out,
            severity=severity,
            title=title,
            description=description,
            cwe=cwe,
            file_path=file_path,
            line=line,
            poc_markdown=poc_markdown,
            evidence=evidence,
        )
        self.append_entry(
            project_id,
            "file_ref",
            f"finding: {rec['finding_id']}",
            rec["informe"],
            tags=["finding", severity],
            metadata={"path": rec["informe"], "finding_id": rec["finding_id"]},
            scope="persistent",
            actor=actor,
            session_id=session_id,
        )
        return {"schema_version": SCHEMA_VERSION, **rec}

    def audit_run(
        self,
        target_directory: str | None = None,
        project_id: str | None = None,
        profile_id: str = "security-full",
        reset: bool = False,
        actor: str = "agent",
        session_id: str | None = None,
    ) -> dict:
        return run_audit(
            self,
            target_directory=target_directory,
            project_id=project_id,
            profile_id=profile_id,
            reset=reset,
            actor=actor,
            session_id=session_id,
        )

    def audit_finalize(self, project_id: str, actor: str = "agent") -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, actor)
            _root, out, _cfg = self.audit_session._output_root(conn, project_id)
        fin = finalize_audit(out)
        if fin["complete"]:
            self.update_summary(
                project_id,
                summary=f"Auditoría finalizada: {fin['finding_count']} findings en disco.",
                checkpoint="audit:finalize:done",
                actor=actor,
            )
        return {"schema_version": SCHEMA_VERSION, **fin}

    def audit_status(self, project_id: str, actor: str = "agent") -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, actor)
            root, out, cfg = self.audit_session._output_root(conn, project_id)
            nxt = self.workspace.next_unit(conn, project_id)
            pending = conn.execute(
                """
                SELECT id, title FROM memory_entries
                WHERE project_id=? AND entry_type='pending' AND deleted_at IS NULL
                ORDER BY sequence DESC LIMIT 10
                """,
                (project_id,),
            ).fetchall()
            st = conn.execute(
                "SELECT summary, checkpoint FROM project_state WHERE project_id=?",
                (project_id,),
            ).fetchone()
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "workspace_path": str(root),
            "output_dir": str(out),
            "profile_id": cfg.get("profile_id"),
            "checkpoint": st["checkpoint"] if st else "",
            "summary": st["summary"] if st else "",
            "next_unit": nxt.get("unit"),
            "open_tasks": [dict(r) for r in pending],
        }

    def audit_next_step(self, project_id: str, actor: str = "agent") -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, actor)
            _root, out, _cfg = self.audit_session._output_root(conn, project_id)
            nxt = self.workspace.next_unit(conn, project_id)
        unit = nxt.get("unit")
        if not unit:
            return {
                "schema_version": SCHEMA_VERSION,
                "project_id": project_id,
                "output_dir": str(out),
                "unit": None,
                "done": True,
                "do_now": f'memory_audit_finalize(project_id="{project_id}")',
            }
        rel = unit.get("read_rel_path") or (unit.get("rel_paths") or [""])[0]
        uid = unit["unit_id"]
        if unit.get("strategy") == "rg_windows":
            do_now = (
                f'memory_workspace_scan_patterns(project_id="{project_id}", rel_path="{rel}")'
            )
        else:
            do_now = (
                f'memory_workspace_read(project_id="{project_id}", rel_path="{rel}")'
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "output_dir": str(out),
            "done": False,
            "unit": {
                "unit_id": uid,
                "read_rel_path": rel,
                "strategy": unit.get("strategy"),
            },
            "do_now": do_now,
            "then": (
                f'memory_audit_complete_step(project_id="{project_id}", unit_id="{uid}")'
            ),
        }

    def audit_complete_step(
        self,
        project_id: str,
        unit_id: str,
        *,
        notes: str = "",
        skip: bool = False,
        actor: str = "agent",
        session_id: str | None = None,
    ) -> dict:
        with self.db.transaction() as conn:
            self._require_active_project(conn, project_id, actor)
            self.workspace.complete_unit(conn, project_id, unit_id, skip=skip)
            nxt = self.workspace.next_unit(conn, project_id)
        ck = f"audit:{unit_id}:done"
        if notes:
            self.append_entry(
                project_id,
                "event",
                f"Unidad {unit_id} cerrada",
                notes[:4000],
                tags=["audit-unit"],
                actor=actor,
                session_id=session_id,
            )
        self.update_summary(
            project_id,
            checkpoint=ck,
            actor=actor,
            session_id=session_id,
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "completed_unit": unit_id,
            "checkpoint": ck,
            "next_unit": nxt.get("unit"),
            "done_all_units": nxt.get("done", False),
            "continue_with": (
                "memory_audit_finalize"
                if nxt.get("done", False)
                else "memory_audit_next_step"
            ),
        }

    def list_audit_profiles(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, "profiles": list_profiles()}

    def list_audit_prompts(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, "prompts": list_prompt_catalog()}

    def get_audit_prompt(
        self, profile_id: str, target_directory: str | None = None
    ) -> dict:
        profile = load_profile(profile_id)
        if target_directory:
            target = Path(target_directory).expanduser().resolve()
            pid = slug_from_path(target)
            out_rel = profile.get("output_dir_default", ".mvp-audit")
            out = target / out_rel
            ctx = {
                "project_id": pid,
                "workspace_path": str(target),
                "output_dir": str(out),
                "findings_dir": str(out / "findings"),
                "poc_dir": str(out / "poc"),
                "scans_dir": str(out / "scans"),
            }
        else:
            ctx = {
                "project_id": "<auto>",
                "workspace_path": "<target_directory>",
                "output_dir": "<target>/.mvp-audit",
                "findings_dir": "<target>/.mvp-audit/findings",
                "poc_dir": "<target>/.mvp-audit/poc",
                "scans_dir": "<target>/.mvp-audit/scans",
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "profile_id": profile_id,
            "prompt_markdown": render_audit_prompt(profile, ctx),
            "config": profile,
        }

