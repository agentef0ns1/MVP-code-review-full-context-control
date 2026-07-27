import pytest

from mvp_memory.config import Settings
from mvp_memory.core.store import MemoryStore


@pytest.fixture
def store(tmp_path):
    settings = Settings.from_args(data_dir=tmp_path / "data")
    return MemoryStore(settings)


def test_get_checkpoint_compact(store):
    pid = "compact-proj"
    store.initialize_if_missing(pid)
    store.append_entry(pid, "decision", "D1", "body" * 200)
    store.append_entry(pid, "pending", "P1", "body" * 200)
    full = store.get_state(pid, auto_create=False, compact=False)
    slim = store.get_checkpoint(pid)
    assert slim["compact"] is True
    assert len(str(full)) > len(str(slim))
    assert "body" not in str(slim["decisions"][0])
