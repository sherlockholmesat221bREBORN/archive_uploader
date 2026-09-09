#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path

STATE_DIR = Path.home() / ".config" / "archive_uploader"
DB_FILE = STATE_DIR / "uploader.db"

def migrate():
    # Search recursively for all .ndjson files in the config tree and working directory
    log_files = set(STATE_DIR.rglob("*.ndjson")) | set(Path(".").rglob("*.ndjson"))
    
    if not log_files:
        print("ℹ️ No .ndjson log files found to migrate.")
        return

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    
    with conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                identifier TEXT PRIMARY KEY,
                upc TEXT,
                qobuz_id TEXT,
                artist TEXT,
                title TEXT,
                status TEXT,
                script_version TEXT,
                script_hash TEXT,
                qobuz_raw_json TEXT,
                mb_raw_json TEXT,
                wiki_raw_json TEXT,
                ia_payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_manifest (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identifier TEXT,
                file_name TEXT,
                file_size INTEGER,
                md5_hash TEXT,
                sha256_hash TEXT,
                audio_spec TEXT,
                raw_flac_tags_json TEXT,
                status TEXT,
                FOREIGN KEY(identifier) REFERENCES uploads(identifier) ON DELETE CASCADE
            )
        """)

    migrated_uploads = 0
    migrated_files = 0

    with conn:
        for filepath in log_files:
            print(f"📦 Processing log file: {filepath}")
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    identifier = record.get("identifier") or record.get("id")
                    if not identifier:
                        continue

                    upc = record.get("upc", "")
                    qobuz_id = record.get("qobuz_id", "")
                    artist = record.get("artist", "")
                    title = record.get("title", "")
                    status = record.get("status", "completed")

                    conn.execute("""
                        INSERT INTO uploads (identifier, upc, qobuz_id, artist, title, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(identifier) DO UPDATE SET
                            upc=COALESCE(NULLIF(excluded.upc, ''), uploads.upc),
                            qobuz_id=COALESCE(NULLIF(excluded.qobuz_id, ''), uploads.qobuz_id),
                            artist=COALESCE(NULLIF(excluded.artist, ''), uploads.artist),
                            title=COALESCE(NULLIF(excluded.title, ''), uploads.title),
                            status=excluded.status,
                            updated_at=CURRENT_TIMESTAMP
                    """, (identifier, upc, qobuz_id, artist, title, status))
                    migrated_uploads += 1

                    files = record.get("files") or record.get("file_manifest") or []
                    if isinstance(files, (list, dict)):
                        file_iterable = files.keys() if isinstance(files, dict) else files
                        for item in file_iterable:
                            fname = item if isinstance(item, str) else item.get("file_name", "")
                            if fname:
                                conn.execute("""
                                    INSERT INTO file_manifest (identifier, file_name, status)
                                    VALUES (?, ?, ?)
                                """, (identifier, fname, status))
                                migrated_files += 1

    print(f"\n✨ [Migration Complete] Migrated {migrated_uploads} upload state(s) and {migrated_files} file record(s) into SQLite.")

if __name__ == "__main__":
    migrate()
