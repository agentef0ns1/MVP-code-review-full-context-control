from __future__ import annotations

import hashlib
import json
import math
import re

from mvp_memory.config import Settings
from mvp_memory.core.db import Database


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{3,}", text.lower())


def _hash_embedding(text: str, dims: int = 64) -> list[float]:
    """Local bag-of-hashes embedding (no external model). v0.2 semantic fallback."""
    vec = [0.0] * dims
    for tok in _tokenize(text):
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        idx = h % dims
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class SemanticSearchService:
    """Optional semantic layer: hash embeddings stored in SQLite (upgrade path to sqlite-vec)."""

    MODEL = "hash-v1"

    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db

    def index_entry(self, entry: dict) -> None:
        if not self.settings.semantic_search_enabled:
            return
        text = f"{entry.get('title', '')} {entry.get('body', '')} {' '.join(entry.get('tags') or [])}"
        vec = _hash_embedding(text)
        conn = self.db.connect()
        conn.execute(
            """
            INSERT INTO entry_embeddings (entry_id, project_id, model, vector_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(entry_id) DO UPDATE SET vector_json=excluded.vector_json, model=excluded.model
            """,
            (entry["id"], entry["project_id"], self.MODEL, json.dumps(vec)),
        )
        conn.commit()

    def search(self, project_id: str, query: str, limit: int = 10) -> list[dict]:
        if not self.settings.semantic_search_enabled:
            return []
        qvec = _hash_embedding(query)
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT entry_id, vector_json FROM entry_embeddings WHERE project_id=?",
            (project_id,),
        ).fetchall()
        scored: list[tuple[float, str]] = []
        for r in rows:
            vec = json.loads(r["vector_json"])
            scored.append((_cosine(qvec, vec), r["entry_id"]))
        scored.sort(reverse=True, key=lambda x: x[0])
        return [
            {"entry_id": eid, "score": score}
            for score, eid in scored[:limit]
            if score > 0.05
        ]
