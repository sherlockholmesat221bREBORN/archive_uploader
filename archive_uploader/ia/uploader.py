"""Internet Archive execution workflow and retry loop."""

import hashlib
from pathlib import Path
from typing import Optional, Set
import internetarchive as ia

from archive_uploader.ia.identifiers import resolve_identifier
from archive_uploader.ia.payload import build_ia_payload, is_valid_payload_file
from archive_uploader.models import Release
from archive_uploader.packaging import delete_local_release, determine_file_key
from archive_uploader.state.store import StateStore, Store
from archive_uploader.textutils import slugify

FATAL_UPLOAD_ERRORS = (
    "access denied", "taken offline", "403", "forbidden",
    "unauthorized", "item is locked", "darked",
)


def get_expected_file_keys(rel: Release) -> Set[str]:
    """Calculates expected remote filenames without running heavy encoding or zipping."""
    expected = set()

    flac_list = [t.path for t in rel.tracks if t.path and t.path.exists()]
    if not flac_list and rel.dir_or_file.is_file():
        flac_list = [rel.dir_or_file]
    elif not flac_list and rel.dir_or_file.is_dir():
        flac_list = sorted([
            p for p in rel.dir_or_file.rglob("*.flac")
            if is_valid_payload_file(p)
        ])

    for flac_p in flac_list:
        expected.add(determine_file_key(flac_p, rel))

    is_single = (
        rel.kind == "single"
        or getattr(rel, "is_single", False)
        or "(SINGLE)" in rel.title.upper()
        or " - SINGLE" in rel.title.upper()
        or len(flac_list) <= 1
    )

    if not is_single:
        base = f"{rel.artist} {rel.title}".strip() or rel.dir_or_file.name
        slug_name = slugify(base)
        expected.add(f"{slug_name}-flac-complete.zip")
        expected.add(f"{slug_name}-opus-complete.zip")

    return expected


def check_remote_manifest(item_id: str, expected_keys: Set[str]) -> tuple[bool, Set[str]]:
    """
    Checks if an IA item exists and whether its remote manifest contains all expected files.
    Returns (is_complete, missing_keys).
    """
    try:
        item = ia.get_item(item_id)
        if not getattr(item, "exists", False):
            return False, expected_keys

        remote_files = {f.name for f in item.get_files()}
        missing = expected_keys - remote_files
        return len(missing) == 0, missing
    except Exception:
        return False, expected_keys


def check_upc_match(rel: Release, expected_keys: Set[str]) -> Optional[str]:
    """Searches IA for the UPC, verifies artist/ownership, and checks manifest completeness."""
    if not rel.upc:
        return None

    try:
        results = list(ia.search_items(f'"{rel.upc}"'))
        for res in results:
            target_id = res.get("identifier")
            if not target_id:
                continue

            item = ia.get_item(target_id)
            meta = getattr(item, "metadata", {})

            # Verify ownership: check matching UPC field or matching artist name
            remote_upc = meta.get("upc") or meta.get("barcode")
            remote_creator = str(meta.get("creator", "")).lower()
            artist_match = rel.artist.lower() in remote_creator

            if remote_upc == rel.upc or artist_match:
                is_complete, missing = check_remote_manifest(target_id, expected_keys)
                if is_complete:
                    return target_id
                else:
                    print(f"  -> Found UPC match '{target_id}', but upload is missing {len(missing)} file(s). Resuming...")
    except Exception:
        pass

    return None


def upload_release(
    rel: Release,
    collection: str,
    mediatype: str,
    dry_run: bool = False,
    delete_after: bool = False,
    state: Optional[StateStore] = None,
    opus_bitrate: str = "192k",
) -> None:
    """Executes pre-checks against DB and live IA manifests before triggering heavy payload creation."""
    store = state or Store()

    # Fast path: Local DB check
    qobuz_id = rel.provider_ids.get("qobuz", "")
    if (rel.upc and store.is_uploaded(rel.upc)) or (qobuz_id and store.is_uploaded(qobuz_id)):
        print(f"  -> [SKIPPED] Release '{rel.artist} - {rel.title}' complete in local DB.")
        if delete_after and not dry_run:
            delete_local_release(rel)
        return

    # Derive identifier & compute expected lightweight keys
    base = f"{rel.artist} {rel.title}".strip() or rel.dir_or_file.name
    id_hash = hashlib.md5(base.encode("utf-8")).hexdigest()[:8]
    identifier = resolve_identifier(base, id_hash, store)
    expected_keys = get_expected_file_keys(rel)

    # Check local store for identifier
    if store.is_uploaded(identifier):
        print(f"  -> [SKIPPED] '{identifier}' complete in local DB state.")
        if delete_after and not dry_run:
            delete_local_release(rel)
        return

    # Check live IA remote manifest for direct identifier
    is_complete, missing_keys = check_remote_manifest(identifier, expected_keys)
    if is_complete:
        print(f"  -> [SKIPPED] '{identifier}' already fully uploaded on Internet Archive.")
        if hasattr(store, "mark_uploaded"):
            store.mark_uploaded(identifier, expected_keys)
        if delete_after and not dry_run:
            delete_local_release(rel)
        return
    elif len(missing_keys) < len(expected_keys):
        print(f"  -> [RESUMING] '{identifier}' exists on IA but is incomplete ({len(missing_keys)} files missing).")

    # Check live IA remote manifest via UPC search if direct ID didn't hit
    if len(missing_keys) == len(expected_keys):
        existing_upc_id = check_upc_match(rel, expected_keys)
        if existing_upc_id:
            print(f"  -> [SKIPPED] Release matched via UPC to fully uploaded item '{existing_upc_id}'.")
            if hasattr(store, "mark_uploaded"):
                store.mark_uploaded(existing_upc_id, expected_keys)
            if delete_after and not dry_run:
                delete_local_release(rel)
            return

    # Heavy payload generation (Opus conversion & ZIP archives) ONLY if incomplete/missing
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
