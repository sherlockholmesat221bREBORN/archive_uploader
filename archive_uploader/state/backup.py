"""
Numbered snapshots of the (tiny, append-only) state logs. Call
snapshot_logs() periodically — once per run is plenty — and you get a
new backups/<device>_00042.ndjson every time, with no metadata to
maintain and no message to write.

Because the logs are the source of truth and are append-only, a backup
is also automatically a version: replaying <device>_00041.ndjson gives
you exactly the upload state as of that snapshot.

Sync the whole `backups/` (or even just `logs/`) directory with
whatever you already use to move files between devices (Syncthing,
etc.) for off-device redundancy.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from ..config import BACKUPS_DIR, LOGS_DIR


def _next_counter(backups_dir: Path, device: str) -> int:
    counter_file = backups_dir / f"{device}.counter"
    n = int(counter_file.read_text().strip()) + 1 if counter_file.exists() else 1
    counter_file.write_text(str(n))
    return n


def snapshot_logs(logs_dir: Path = LOGS_DIR, backups_dir: Path = BACKUPS_DIR) -> List[Path]:
    backups_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for log_file in sorted(logs_dir.glob("*.ndjson")):
        device = log_file.stem
        n = _next_counter(backups_dir, device)
        dest = backups_dir / f"{device}_{n:05d}.ndjson"
        shutil.copy2(log_file, dest)
        created.append(dest)
    return created


def list_backups(device: str, backups_dir: Path = BACKUPS_DIR) -> List[Path]:
    return sorted(backups_dir.glob(f"{device}_*.ndjson"))
