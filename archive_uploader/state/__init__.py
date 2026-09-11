from archive_uploader.state.store import SQLiteStateStore
from archive_uploader.state.log_store import LogStateStore
from archive_uploader.state.combined import CombinedStateStore

# Previously: "Set SQLite as the primary and only state store engine" —
# StateStore = Store = SQLiteStateStore. That line is the actual reason
# log_store.py (README: "the real implementation") was never consulted
# anywhere: every caller asks for Store()/StateStore() by these names.
# CombinedStateStore wires the per-device log in alongside SQLite instead
# of replacing it — see state/combined.py and DECISIONS.md.
StateStore = CombinedStateStore
Store = CombinedStateStore

__all__ = ["SQLiteStateStore", "LogStateStore", "CombinedStateStore", "StateStore", "Store"]
