"""Self-backup, log snapshotting, and script recoverability engine."""

import hashlib
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from archive_uploader import __version__

BACKUP_DIR = Path.home() / ".config" / "archive_uploader" / "backups"
LOGS_DIR = Path.home() / ".config" / "archive_uploader" / "logs"


def ensure_script_backup() -> Tuple[Path, str]:
    """
    Hashes the running package/script with SHA-256 and creates a version-locked backup copy.
    Returns a tuple of (backup_filepath, sha256_hash).
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    main_pkg = Path(__file__).resolve().parent.parent
    if main_pkg.is_dir() and (main_pkg / "__init__.py").exists():
        hasher = hashlib.sha256()
        for p in sorted(main_pkg.rglob("*.py")):
            hasher.update(p.read_bytes())
        script_hash = hasher.hexdigest()

        backup_file = BACKUP_DIR / f"archive_uploader-v{__version__}-{script_hash[:8]}.tar.gz"
        if not backup_file.exists():
            shutil.make_archive(
                str(backup_file).replace(".tar.gz", ""),
                "gztar",
                root_dir=main_pkg.parent,
                base_dir=main_pkg.name,
            )
    else:
        script_path = Path(sys.argv[0]).resolve()
        script_bytes = script_path.read_bytes() if script_path.exists() else b"archive_uploader"
        script_hash = hashlib.sha256(script_bytes).hexdigest()

        backup_file = BACKUP_DIR / f"archive_uploader-v{__version__}-{script_hash[:8]}.py"
        if not backup_file.exists():
            backup_file.write_bytes(script_bytes)

    return backup_file, script_hash


def snapshot_logs(target_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Creates a timestamped snapshot archive of local application logs for debugging and recovery.
    Returns the path to the created archive or None if no logs exist.
    """
    if not LOGS_DIR.exists():
        return None

    log_files = [p for p in LOGS_DIR.rglob("*") if p.is_file()]
    if not log_files:
        return None

    dest_dir = target_dir or (BACKUP_DIR / "log_snapshots")
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_base = dest_dir / f"logs_snapshot_{timestamp}"

    try:
        archive_path = Path(
            shutil.make_archive(
                str(archive_base),
                "gztar",
                root_dir=LOGS_DIR.parent,
                base_dir=LOGS_DIR.name,
            )
        )
        return archive_path
    except Exception as e:
        print(f"  ! Warning: Failed to snapshot logs: {e}")
        return None
