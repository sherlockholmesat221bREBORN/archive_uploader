"""
The rest of the codebase talks to a StateStore, never to a specific
file format. Swapping the log-based implementation for something else
later (Turso, sqlite, whatever) means writing one new class here —
nothing in ia/uploader.py or cli.py has to change.
"""
from __future__ import annotations

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
