"""
State storage interface and default SQLite concrete implementation.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Protocol, Set


class StateStore(Protocol):
    def is_uploaded(self, identifier: str) -> bool:
        """Local-cache answer only. Never trusted alone for the actual
        upload decision — ia/uploader.py always re-checks the live IA
        file manifest before skipping, so this only saves an API call,
        it never causes a missed upload if it's stale or absent."""
        ...

    def mark_uploaded(self, identifier: str, files: Iterable[str]) -> None:
        ...

    def all_uploaded(self) -> Set[str]:
        ...


class SQLiteStateStore:
    def __init__(self, db_path: str | Path = "archive_uploader_state.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    identifier TEXT PRIMARY KEY,
                    files TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def is_uploaded(self, identifier: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM uploads WHERE identifier = ?", (identifier,))
            return cur.fetchone() is not None

    def mark_uploaded(self, identifier: str, files: Iterable[str]) -> None:
        files_str = ",".join(files)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO uploads (identifier, files) VALUES (?, ?)",
                (identifier, files_str),
            )
            conn.commit()

    def all_uploaded(self) -> Set[str]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT identifier FROM uploads")
            return {row[0] for row in cur.fetchall()}


# Concrete alias so existing imports succeed
Store = SQLiteStateStore
