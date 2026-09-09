from archive_uploader.state.store import SQLiteStateStore

# Set SQLite as the primary and only state store engine
StateStore = SQLiteStateStore
Store = SQLiteStateStore

__all__ = ["SQLiteStateStore", "StateStore", "Store"]

