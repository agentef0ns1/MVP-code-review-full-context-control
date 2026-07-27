import pytest

from mvp_memory.config import Settings, project_id_from_workspace
from mvp_memory.core.errors import MemoryError
from mvp_memory.core.store import MemoryStore


@pytest.fixture
def store(tmp_path):
    settings = Settings.from_args(data_dir=tmp_path / "data")
    return MemoryStore(settings)


def test_auto_init_idempotent(store):
    pid = "test-proj-abc123"
    s1, created1 = store.initialize_if_missing(pid)
    assert created1 is True
    s2, created2 = store.initialize_if_missing(pid)
    assert created2 is False
    state = store.get_state(pid, auto_create=False)
    assert state["project_id"] == pid
    assert "summary" in state


def test_append_search_fts(store):
    pid = "fts-proj"
    store.initialize_if_missing(pid)
    store.append_entry(pid, "event", "Auth module", "JWT validation missing in login.py", tags=["auth", "security"])
    store.update_summary(pid, summary="Reviewed auth", checkpoint="auth:partial")
    hits = store.search(pid, "JWT login")
    assert hits["count"] >= 1
    assert any("Auth" in e["title"] for e in hits["entries"])


def test_versioning_on_update(store):
    pid = "ver-proj"
    store.initialize_if_missing(pid)
    r = store.append_entry(pid, "decision", "Use SQLite", "Local DB for PoC")
    eid = r["entry"]["id"]
    store.update_entry(eid, body="Local DB for PoC v2", reason="clarify", actor="human")
    versions = store.entry_versions(eid)
    assert len(versions["versions"]) >= 2


def test_soft_delete_requires_confirm(store):
    pid = "del-proj"
    store.initialize_if_missing(pid)
    r = store.append_entry(pid, "event", "temp", "x")
    eid = r["entry"]["id"]
    with pytest.raises(MemoryError) as exc:
        store.delete_entry(eid, "nope", confirm=False)
    assert exc.value.code == "confirm_required"
    store.delete_entry(eid, "ok", confirm=True)
    with pytest.raises(MemoryError):
        store.get_entry(eid)


def test_audit_on_init(store):
    pid = "audit-proj"
    store.initialize_if_missing(pid)
    log = store.list_audit(project_id=pid)
    actions = [i["action"] for i in log["items"]]
    assert "project.created" in actions


def test_lock_acquire_release(store):
    pid = "lock-proj"
    store.initialize_if_missing(pid)
    with store.db.transaction() as conn:
        acq = store.locks.acquire(conn, pid, "test-session", 60)
    token = acq["token"]
    with store.db.transaction() as conn:
        store.locks.release(conn, pid, token)
    st = store.lock_status(pid)
    assert st["locked"] is False


def test_project_id_from_workspace():
    pid = project_id_from_workspace("/tmp/my-app")
    assert pid.startswith("my-app-")
    assert len(pid.split("-")[-1]) == 6


def test_export_import_roundtrip(store, tmp_path):
    pid = "roundtrip"
    store.initialize_if_missing(pid)
    store.append_entry(pid, "event", "hello", "world")
    meta = store.export_project(pid)
    path = meta["path"]
    data = open(path, encoding="utf-8").read()
    store.import_project(data, mode="merge")
    state = store.get_state(pid, auto_create=False)
    assert state["stats"]["entry_count"] >= 2
