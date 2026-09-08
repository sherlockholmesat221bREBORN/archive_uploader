"""
Each device appends to its own file: state/logs/<device_id>.ndjson.
No device ever writes another device's file, so there is no concurrent-
write hazard even if the logs directory is synced (Syncthing, a synced
folder, whatever) between devices with genuinely unpredictable timing —
the sync layer only ever has to move whole files around, never merge
their contents. See DECISIONS.md for why this beats a shared SQLite
file over a sync layer.

Reading is a full replay of every *.ndjson file in the directory. At
personal-library scale (thousands of releases, not millions) this is
fast enough to just do on every call rather than caching and risking
staleness bugs.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, List, Set

from ..config import LOGS_DIR, get_device_id


class LogStateStore:
    def __init__(self, logs_dir: Path = LOGS_DIR, device_id: str | None = None):
        self.logs_dir = logs_dir
        self.device_id = device_id or get_device_id()
        self.own_log = self.logs_dir / f"{self.device_id}.ndjson"

    # -- writing --------------------------------------------------------
    # Only ever appends to self.own_log. Never opens another device's
    # log for writing.

    def mark_uploaded(self, identifier: str, files: Iterable[str]) -> None:
        event = {
            "event": "uploaded",
            "identifier": identifier,
            "files": sorted(files),
            "ts": time.time(),
        }
        with open(self.own_log, "a") as f:
            f.write(json.dumps(event) + "\n")

    # -- reading ----------------------------------------------------------

    def _iter_events(self):
        for log_file in sorted(self.logs_dir.glob("*.ndjson")):
            try:
                with open(log_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            # A partial/torn write from a crash mid-append.
                            # Skip it rather than fail the whole read —
                            # the IA live check is still the real backstop.
                            continue
            except FileNotFoundError:
                continue

    def all_uploaded(self) -> Set[str]:
        return {e["identifier"] for e in self._iter_events() if e.get("event") == "uploaded"}

    def is_uploaded(self, identifier: str) -> bool:
        return identifier in self.all_uploaded()

    def all_log_files(self) -> List[Path]:
        return sorted(self.logs_dir.glob("*.ndjson"))
