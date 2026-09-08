from __future__ import annotations

import sys
import time

import internetarchive as ia

from ..models import Release
from ..packaging import delete_local_release
from ..state.store import StateStore
from .payload import build_ia_payload


def upload_release(
    rel: Release,
    collection: str,
    mediatype: str,
    dry_run: bool,
    delete_after: bool,
    state: StateStore,
) -> None:
    known_identifiers = state.all_uploaded()
    identifier, metadata, files_dict, temp_cleanup_files = build_ia_payload(
        rel, collection, mediatype, known_identifiers
    )

    try:
        if state.is_uploaded(identifier):
            print(f"  -> [SKIPPED] '{identifier}' complete in local state.")
            if delete_after and not dry_run:
                delete_local_release(rel)
            return

        # The local state store is only ever a cache. This live check
        # against IA is the actual source of truth for "is it already
        # there" — it's what makes multiple devices safe without any
        # coordination between them. Don't remove it to "simplify."
        item = ia.get_item(identifier)
        if item.exists:
            try:
                remote_file_objects = list(item.get_files())
                remote_files = {f.name for f in remote_file_objects}
                local_files = set(files_dict.keys())

                is_multidisc_upload = any("/" in key for key in local_files)
                if is_multidisc_upload:
                    orphaned_root_flacs = [
                        f.name
                        for f in remote_file_objects
                        if (f.name.endswith(".flac") or f.name.endswith(".opus"))
                        and "/" not in f.name
                    ]
                    if orphaned_root_flacs:
                        print(
                            f"\n  -> [REPAIR MODE] Found {len(orphaned_root_flacs)} "
                            f"misplaced root-level file(s) from previous upload."
                        )
                        print("     Purging root files from IA before uploading structured multi-disc folders...")
                        if not dry_run:
                            ia.delete(identifier, files=orphaned_root_flacs)
                            remote_files -= set(orphaned_root_flacs)

                missing_files = local_files - remote_files

                if not missing_files:
                    print(f"  -> [SKIPPED] '{identifier}' is completely present on IA.")
                    state.mark_uploaded(identifier, files_dict.keys())
                    if delete_after and not dry_run:
                        delete_local_release(rel)
                    return
                else:
                    print(f"\n  -> [RESUMING / REPAIRING UPLOAD] '{identifier}'")
                    print(
                        f"     Found {len(remote_files)} file(s) online. "
                        f"Uploading {len(missing_files)} missing file(s)..."
                    )
                    files_dict = {k: v for k, v in files_dict.items() if k in missing_files}
            except Exception as e:
                print(f"  ! Error checking remote file manifest ({e}). Proceeding with standard sync...")

        print(f"\n Uploading to Internet Archive: {identifier}")
        print(f"   Title:   {metadata['title']}")
        print(f"   UPC:     {metadata.get('upc', '(none)')}")
        print(f"   Files:   {len(files_dict)} item(s) to upload")

        if dry_run:
            print("   [DRY RUN] Skipping actual network upload and deletion.")
            return

        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
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
                    print("   \u2713 Upload complete. Triggering background MP3 derivation...")
                    item.derive()
                    state.mark_uploaded(identifier, files_dict.keys())

                    if delete_after:
                        delete_local_release(rel)
                    return
            except KeyboardInterrupt:
                print("\n  ! Upload interrupted by user (Ctrl+C). Local files preserved. Exiting...")
                sys.exit(0)
            except Exception as e:
                print(f"  ! Upload attempt {attempt} failed: {e}")

            sleep_time = attempt * 10
            print(f"  ! Retrying in {sleep_time} seconds...")
            time.sleep(sleep_time)

        print(f"  \u2715 Failed to complete upload for '{identifier}'. Local files retained.")
    finally:
        for tmp in temp_cleanup_files:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
