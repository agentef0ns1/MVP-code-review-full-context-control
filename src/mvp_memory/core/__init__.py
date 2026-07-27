"""Domain core package."""

from mvp_memory.core.errors import MemoryError

__all__ = ["MemoryError"]


def __getattr__(name: str):
    if name == "MemoryStore":
        from mvp_memory.core.store import MemoryStore

        return MemoryStore
    raise AttributeError(name)
