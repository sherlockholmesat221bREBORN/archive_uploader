"""
Central configuration: filesystem layout and device identity.

Everything else in the package imports paths from here rather than
building its own — that's the seam that keeps "where does state live"
a one-line change instead of a grep-and-replace.
"""
from __future__ import annotations

import os
import platform
import uuid
from pathlib import Path

# --------------------------------------------------------------------------
# Filesystem layout
# --------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".config" / "archive_uploader"
STATE_DIR = CONFIG_DIR / "state"
LOGS_DIR = STATE_DIR / "logs"          # per-device append-only event logs
BACKUPS_DIR = STATE_DIR / "backups"    # numbered log snapshots
CACHE_DIR = CONFIG_DIR / "metadata_cache"  # raw provider responses, never hand-edited
TEMP_DIR = Path(os.environ.get("TMPDIR", "/tmp")) / "archive_uploader"

for d in (CONFIG_DIR, STATE_DIR, LOGS_DIR, BACKUPS_DIR, CACHE_DIR, TEMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

DEVICE_ID_FILE = CONFIG_DIR / "device_id"

# --------------------------------------------------------------------------
# Device identity
# --------------------------------------------------------------------------

def get_device_id() -> str:
    """
    Stable per-device id. Each device only ever writes to its own log file
    (see state/log_store.py), so this id is the sharding key that makes
    concurrent multi-device writes safe without any locking or server.
    """
    override = os.environ.get("ARCHIVE_UPLOADER_DEVICE_ID")
    if override:
        return override

    if DEVICE_ID_FILE.exists():
        return DEVICE_ID_FILE.read_text().strip()

    host = platform.node().split(".")[0].lower() or "device"
    device_id = f"{host}-{uuid.uuid4().hex[:8]}"
    DEVICE_ID_FILE.write_text(device_id)
    return device_id

# --------------------------------------------------------------------------
# Misc shared constants
# --------------------------------------------------------------------------

SYSTEM_EXCLUDES = {".ds_store", "thumbs.db", "desktop.ini", "@eadir"}


def is_valid_asset(p: Path) -> bool:
    if p.name.startswith("."):
        return False
    if p.name.lower() in SYSTEM_EXCLUDES:
        return False
    return True
