"""Self-backup and script recoverability engine."""

import hashlib
import shutil
import sys
from pathlib import Path
from typing import Tuple

from archive_uploader import __version__

BACKUP_DIR = Path.home() / ".config" / "archive_uploader" / "backups"


def ensure_script_backup() -> Tuple[Path, str]:
    """
    Hashes the running package/script with SHA-256 and creates a version-locked backup copy.
    Returns a tuple of (backup_filepath, sha256_hash).
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Determine running entrypoint or module location
    main_pkg = Path(__file__).resolve().parent.parent
    if main_pkg.is_dir():
        # Package mode: create hash from version and file structure
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
        # Monolith / single file mode fallback
        script_path = Path(sys.argv[0]).resolve()
        script_bytes = script_path.read_bytes()
        script_hash = hashlib.sha256(script_bytes).hexdigest()
        
        backup_file = BACKUP_DIR / f"archive_uploader-v{__version__}-{script_hash[:8]}.py"
        if not backup_file.exists():
            backup_file.write_bytes(script_bytes)

    return backup_file, script_hash
