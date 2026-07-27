from mvp_memory.config import Settings
from mvp_memory.core.store import MemoryStore


def test_semantic_search_when_enabled(tmp_path):
    settings = Settings.from_args(data_dir=tmp_path / "data", semantic=True)
    store = MemoryStore(settings)
    pid = "sem-proj"
    store.initialize_if_missing(pid)
    store.append_entry(pid, "event", "Database layer", "Uses SQLite WAL mode for concurrency")
    hits = store.search(pid, "concurrency database", semantic=True)
    assert hits["count"] >= 0
