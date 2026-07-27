from __future__ import annotations

import json

from mvp_memory.core.db import Database, row_to_dict


class SearchService:
    def search(
        self,
        project_id: str,
        query: str,
        types: list[str] | None = None,
        tags: list[str] | None = None,
        since: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        conn = self.db.connect()
        limit = min(max(limit, 1), 100)
        hits: list[dict] = []

        if query.strip():
            fts_query = " ".join(f'"{part}"' for part in query.split() if part)
            if not fts_query:
                fts_query = query
            try:
                rows = conn.execute(
                    """
                    SELECT entry_id, bm25(fts_memory) AS rank
                    FROM fts_memory
                    WHERE fts_memory MATCH ? AND project_id = ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, project_id, limit * 3),
                ).fetchall()
            except Exception:
                rows = conn.execute(
                    """
                    SELECT entry_id, 0 AS rank FROM fts_memory
                    WHERE project_id=? AND (title LIKE ? OR body LIKE ?)
                    LIMIT ?
                    """,
                    (project_id, f"%{query}%", f"%{query}%", limit * 3),
                ).fetchall()
            for r in rows:
                hits.append({"entry_id": r["entry_id"], "score": float(-r["rank"]) if r["rank"] else 0.0})
        else:
            rows = conn.execute(
                """
                SELECT id AS entry_id FROM memory_entries
                WHERE project_id=? AND deleted_at IS NULL
                ORDER BY sequence DESC LIMIT ?
                """,
                (project_id, limit * 3),
            ).fetchall()
            hits = [{"entry_id": r["entry_id"], "score": 0.0} for r in rows]

        if not hits:
            return []

        filtered: list[dict] = []
        for hit in hits:
            row = conn.execute(
                "SELECT * FROM memory_entries WHERE id=? AND deleted_at IS NULL",
                (hit["entry_id"],),
            ).fetchone()
            if not row:
                continue
            entry = row_to_dict(row)
            if types and entry["entry_type"] not in types:
                continue
            tag_list = json.loads(entry.get("tags_json") or "[]")
            if tags and not all(t in tag_list for t in tags):
                continue
            if since and (entry.get("created_at") or "") < since:
                continue
            filtered.append(hit)
            if len(filtered) >= limit:
                break
        return filtered

    def __init__(self, db: Database) -> None:
        self.db = db
