"""Optional SQLCipher integration (v0.2 placeholder).

Set MVP_MEMORY_SQLCIPHER=1 to flag intent. Full encryption requires linking against
SQLCipher and using pysqlcipher3; the PoC uses standard sqlite3 in db.py.
"""

from mvp_memory.config import Settings


def sqlcipher_note(settings: Settings) -> str | None:
    if settings.sqlcipher_enabled:
        return (
            "SQLCipher requested but not linked in this build; using plain SQLite. "
            "See README for future integration."
        )
    return None
