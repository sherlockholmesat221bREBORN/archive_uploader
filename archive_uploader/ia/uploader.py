"""Internet Archive execution workflow and retry loop."""

import hashlib
import time
from typing import Optional, Set
import internetarchive as ia

from archive_uploader.ia.identifiers import resolve_identifier
from archive_uploader.ia.payload import build_ia_payload
from archive_uploader.models import Release
from archive_uploader.packaging import delete_local_release
from archive_uploader.state.store import StateStore, Store

FATAL_UPLOAD_ERRORS = (
    "access denied", "taken offline", "403", "forbidden",
    "unauthorized", "item is locked", "darked",
)


def check_remote_ia(identifier: str, upc: Optional[str] = None) -> bool:
    """Queries Internet Archive remotely for item identifier or UPC match."""
    try:
        item = ia.get_item(identifier)
        if getattr(item, "exists", False):
            return True
    except Exception:
        pass

    if upc:
        try:
            results = list(ia.search_items(f'"{upc}"'))
            if len(results) > 0:
                return True
        except Exception:
            pass

    return False


def upload_release(
    rel: Release,
    collection: str,
    mediatype: str,
    dry_run: bool = False,
    delete_after: bool = False,
    state: Optional[StateStore] = None,
    opus_bitrate: str = "192k",
) -> None:
    """Executes pre-checks against DB/IA state, builds payload, and uploads release."""
    store = state or Store()

    # 1. Local DB Pre-check
    qobuz_id = rel.provider_ids.get("qobuz", "")
    if (
        (rel.upc and store.is_uploaded(rel.upc))
        or (qobuz_id and store.is_uploaded(qobuz_id))
    ):
        print(f"  -> [SKIPPED] Release '{rel.artist} - {rel.title}' is completed in local DB.")
        if delete_after and not dry_run:
            delete_local_release(rel)
        return

    # 2. Derive identifier early
    base = f"{rel.artist} {rel.title}".strip() or rel.dir_or_file.name
    id_hash = hashlib.md5(base.encode("utf-8")).hexdigest()[:8]
    identifier = resolve_identifier(base, id_hash, store)

    # 3. Check local DB state
    if store.is_uploaded(identifier):
        print(f"  -> [SKIPPED] '{identifier}' complete in local DB state.")
        if delete_after and not dry_run:
            delete_local_release(rel)
        return

    # 4. Check Internet Archive remotely before doing any work
    if check_remote_ia(identifier, rel.upc):
        print(f"  -> [SKIPPED] '{identifier}' already exists on Internet Archive.")
        if hasattr(store, "mark_uploaded"):
            store.mark_uploaded(identifier, [])
        if delete_after and not dry_run:
            delete_local_release(rel)
        return

    # 5. Build heavy payload ONLY if missing from IA and local DB
    identifier, metadata, files_dict, temp_cleanup_files = build_ia_payload(
        rel, collection, mediatype, known_identifiers=store, opus_bitrate=opus_bitrate
    )

    try:
        if dry_run:
            print(f"  [DRY RUN] Prepared upload payload for '{identifier}' ({len(files_dict)} files).")
            return

        responses = ia.upload(
            identifier,
            files=files_dict,
            metadata=metadata,
            verbose=True,
            retries=10,
            retries_sleep=20,
            checksum=True,
        )

        if all(getattr(r, "status_code", 200) < 400 for r in responses):
            print("   ✓ Upload complete.")
            if hasattr(store, "mark_uploaded"):
                store.mark_uploaded(identifier, files_dict.keys())
            if delete_after:
                delete_local_release(rel)

    except Exception as e:
        err_msg = str(e).lower()
        if any(fatal in err_msg for fatal in FATAL_UPLOAD_ERRORS):
            print(f"  ⛔ [FATAL ERROR] Item locked or taken offline by IA: {e}")
        else:
            print(f"  ! Upload failed: {e}")
    finally:
        for tmp in temp_cleanup_files:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
