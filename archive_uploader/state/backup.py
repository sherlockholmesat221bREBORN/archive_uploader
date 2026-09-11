"""Self-backup, log snapshotting, and script recoverability engine."""

import hashlib
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from archive_uploader import __version__
# Previously redefined locally as Path.home()/".config"/"archive_uploader"/"backups"
# and .../"logs" — missing the "state/" segment config.py actually uses
# (STATE_DIR = CONFIG_DIR/"state"), so snapshot_logs() was always checking
# an empty directory and silently returning None. Import the real ones.
from ..config import BACKUPS_DIR as BACKUP_DIR, LOGS_DIR


def compute_script_hash() -> str:
    """
    SHA-256 over every .py file in the running package, without writing
    an archive to disk. Used for the `uploader_script_sha256` IA metadata
    field now that payload.py links to GitHub instead of uploading a
    tarball per item (see get_repo_ref below) — ensure_script_backup()
    below still exists for anyone who wants a local .tar.gz backup, it's
    just no longer called from the upload path.
    """
    main_pkg = Path(__file__).resolve().parent.parent
    hasher = hashlib.sha256()
    for p in sorted(main_pkg.rglob("*.py")):
        hasher.update(p.read_bytes())
    return hasher.hexdigest()


def get_repo_ref() -> str:
    """
    Current commit SHA of the running checkout, for building a
    reproducible-forever GitHub link (…/tree/<sha> instead of …/tree/main,
    which drifts). Falls back to "main" if this isn't a git checkout
    (e.g. installed via pip with no .git directory) or git isn't
    available — never raises.
    """
    main_pkg = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(main_pkg), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "main"


def ensure_script_backup() -> Tuple[Path, str]:
    """
    Hashes the running package/script with SHA-256 and creates a version-locked backup copy.
    Returns a tuple of (backup_filepath, sha256_hash).

    No longer called from ia/payload.py (which now links to GitHub via
    get_repo_ref() instead of uploading this tarball to every IA item) —
    kept here in case you still want local .tar.gz backups for something
    else.
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
