from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mvp_memory.config import Settings
from mvp_memory.core.errors import MemoryError
from mvp_memory.core.store import MemoryStore

STATIC_DIR = Path(__file__).resolve().parent / "static"


class AppState:
    settings: Settings
    store: MemoryStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_args()
    settings.ensure_dirs()
    store = MemoryStore(settings)
    app = FastAPI(title="MVP Memory Context Admin", version="0.2.0")
    app.state.ctx = AppState()
    app.state.ctx.settings = settings
    app.state.ctx.store = store

    def get_store() -> MemoryStore:
        return app.state.ctx.store

    def verify_token(
        authorization: Annotated[str | None, Header()] = None,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> None:
        token = settings.get_or_create_admin_token()
        provided = None
        if authorization and authorization.lower().startswith("bearer "):
            provided = authorization[7:].strip()
        elif x_admin_token:
            provided = x_admin_token.strip()
        if provided != token:
            raise HTTPException(status_code=401, detail="Invalid admin token")

    @app.get("/", response_class=HTMLResponse)
    def index():
        index_path = STATIC_DIR / "index.html"
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @app.get("/api/health")
    def health():
        return {"ok": True, "data_dir": str(settings.data_dir)}

    @app.get("/api/auth/setup")
    def auth_setup(_: None = Depends(verify_token)):
        return {"message": "Token valid", "token_path": str(settings.admin_token_path())}

    @app.get("/api/projects")
    def list_projects(
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        _: None = Depends(verify_token),
        store: MemoryStore = Depends(get_store),
    ):
        try:
            return store.list_projects(status, limit, offset)
        except MemoryError as e:
            raise HTTPException(400, detail={"code": e.code, "message": str(e)}) from e

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str, _: None = Depends(verify_token), store: MemoryStore = Depends(get_store)):
        try:
            state = store.get_state(project_id, auto_create=False, actor="human")
            lock = store.lock_status(project_id)
            return {**state, "lock": lock}
        except MemoryError as e:
            raise HTTPException(404, detail={"code": e.code, "message": str(e)}) from e

    @app.get("/api/projects/{project_id}/timeline")
    def timeline(
        project_id: str,
        limit: int = 100,
        offset: int = 0,
        entry_type: str | None = None,
        _: None = Depends(verify_token),
        store: MemoryStore = Depends(get_store),
    ):
        conn = store.db.connect()
        store.get_project_row(project_id)
        if entry_type:
            rows = conn.execute(
                """
                SELECT * FROM memory_entries
                WHERE project_id=? AND entry_type=? AND deleted_at IS NULL
                ORDER BY sequence DESC LIMIT ? OFFSET ?
                """,
                (project_id, entry_type, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM memory_entries
                WHERE project_id=? AND deleted_at IS NULL
                ORDER BY sequence DESC LIMIT ? OFFSET ?
                """,
                (project_id, limit, offset),
            ).fetchall()
        entries = [store._entry_dict(r) for r in rows]
        return {"schema_version": 1, "entries": entries}

    class EntryCreate(BaseModel):
        entry_type: str = "event"
        title: str
        body: str = ""
        tags: list[str] = Field(default_factory=list)
        metadata: dict = Field(default_factory=dict)
        scope: str = "working"
        human_only: bool = False

    @app.post("/api/projects/{project_id}/entries")
    def create_entry(
        project_id: str,
        body: EntryCreate,
        request: Request,
        _: None = Depends(verify_token),
        store: MemoryStore = Depends(get_store),
    ):
        try:
            with store.db.transaction() as conn:
                store._require_active_project(conn, project_id, "human")
                entry = store._insert_entry_unlocked(
                    conn,
                    project_id=project_id,
                    entry_type=body.entry_type,
                    title=body.title,
                    body=body.body,
                    tags=body.tags,
                    metadata=body.metadata,
                    scope=body.scope,
                    actor="human",
                    session_id=None,
                    human_only=body.human_only,
                )
                store.audit.log(
                    conn,
                    actor="human",
                    action="entry.created.ui",
                    entity_type="memory_entry",
                    entity_id=entry["id"],
                    project_id=project_id,
                    ip=request.client.host if request.client else None,
                )
            return {"entry": entry}
        except MemoryError as e:
            raise HTTPException(400, detail={"code": e.code, "message": str(e)}) from e

    class EntryUpdate(BaseModel):
        title: str | None = None
        body: str | None = None
        tags: list[str] | None = None
        metadata: dict | None = None
        reason: str = "edited via UI"
        human_only: bool | None = None
        frozen: bool | None = None

    @app.patch("/api/entries/{entry_id}")
    def patch_entry(
        entry_id: str,
        body: EntryUpdate,
        request: Request,
        _: None = Depends(verify_token),
        store: MemoryStore = Depends(get_store),
    ):
        try:
            result = store.update_entry(
                entry_id,
                body.title,
                body.body,
                body.tags,
                body.metadata,
                body.reason,
                "human",
                None,
                body.human_only,
            )
            if body.frozen is not None:
                conn = store.db.connect()
                conn.execute(
                    "UPDATE memory_entries SET frozen=? WHERE id=?",
                    (1 if body.frozen else 0, entry_id),
                )
                conn.commit()
            return result
        except MemoryError as e:
            raise HTTPException(400, detail={"code": e.code, "message": str(e)}) from e

    @app.delete("/api/entries/{entry_id}")
    def delete_entry(
        entry_id: str,
        reason: str = "deleted via UI",
        confirm: bool = True,
        _: None = Depends(verify_token),
        store: MemoryStore = Depends(get_store),
    ):
        try:
            return store.delete_entry(entry_id, reason, confirm, "human")
        except MemoryError as e:
            raise HTTPException(400, detail={"code": e.code, "message": str(e)}) from e

    @app.post("/api/entries/{entry_id}/purge")
    def purge_entry(
        entry_id: str,
        confirm_token: str,
        request: Request,
        _: None = Depends(verify_token),
        store: MemoryStore = Depends(get_store),
    ):
        try:
            return store.purge_entry(
                entry_id,
                confirm_token,
                "human",
                request.client.host if request.client else None,
            )
        except MemoryError as e:
            raise HTTPException(403, detail={"code": e.code, "message": str(e)}) from e

    class SearchBody(BaseModel):
        project_id: str
        query: str = ""
        types: list[str] | None = None
        tags: list[str] | None = None
        since: str | None = None
        limit: int = 20
        semantic: bool | None = None

    @app.post("/api/search")
    def search(body: SearchBody, _: None = Depends(verify_token), store: MemoryStore = Depends(get_store)):
        try:
            return store.search(
                body.project_id,
                body.query,
                body.types,
                body.tags,
                body.since,
                body.limit,
                body.semantic,
            )
        except MemoryError as e:
            raise HTTPException(400, detail={"code": e.code, "message": str(e)}) from e

    @app.get("/api/export/{project_id}")
    def export_project(
        project_id: str,
        format: str = "json",
        _: None = Depends(verify_token),
        store: MemoryStore = Depends(get_store),
    ):
        try:
            meta = store.export_project(project_id, format)
            path = Path(meta["path"])
            return FileResponse(path, filename=path.name, media_type="application/json")
        except MemoryError as e:
            raise HTTPException(404, detail={"code": e.code, "message": str(e)}) from e

    @app.post("/api/import")
    async def import_project(
        request: Request,
        mode: str = "merge",
        confirm_overwrite: bool = False,
        _: None = Depends(verify_token),
        store: MemoryStore = Depends(get_store),
    ):
        raw = await request.body()
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise HTTPException(400, detail="Invalid JSON") from e
        try:
            return store.import_project(
                data,
                mode,
                confirm_overwrite,
                "human",
                request.client.host if request.client else None,
            )
        except MemoryError as e:
            raise HTTPException(400, detail={"code": e.code, "message": str(e)}) from e

    @app.get("/api/audit")
    def audit_log(
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        _: None = Depends(verify_token),
        store: MemoryStore = Depends(get_store),
    ):
        return store.list_audit(project_id, limit, offset)

    @app.get("/api/entries/{entry_id}/versions")
    def entry_versions(entry_id: str, _: None = Depends(verify_token), store: MemoryStore = Depends(get_store)):
        return store.entry_versions(entry_id)

    @app.post("/api/projects/{project_id}/freeze")
    def freeze(project_id: str, reason: str = "frozen via UI", _: None = Depends(verify_token), store: MemoryStore = Depends(get_store)):
        try:
            return store.freeze_project(project_id, reason, "human")
        except MemoryError as e:
            raise HTTPException(400, detail={"code": e.code, "message": str(e)}) from e

    @app.post("/api/projects/{project_id}/reset")
    def reset(
        project_id: str,
        wipe: bool = False,
        confirm: bool = False,
        _: None = Depends(verify_token),
        store: MemoryStore = Depends(get_store),
    ):
        try:
            return store.reset_project(project_id, wipe, confirm, "human")
        except MemoryError as e:
            raise HTTPException(400, detail={"code": e.code, "message": str(e)}) from e

    @app.post("/api/projects/{project_id}/lock/break")
    def break_lock(project_id: str, _: None = Depends(verify_token), store: MemoryStore = Depends(get_store)):
        with store.db.transaction() as conn:
            return store.locks.break_glass(conn, project_id)

    @app.exception_handler(MemoryError)
    async def memory_error_handler(_: Request, exc: MemoryError):
        return JSONResponse(status_code=400, content={"code": exc.code, "message": str(exc)})

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


def main() -> None:
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="MVP Memory Context Admin API")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--semantic", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_args(
        data_dir=args.data_dir,
        api_host=args.host,
        api_port=args.port,
        semantic=args.semantic,
    )
    app = create_app(settings)
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="info")


if __name__ == "__main__":
    main()
