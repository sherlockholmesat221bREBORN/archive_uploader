"""Internet Archive item identifier resolution and legacy collision handling."""

from typing import Any, Optional
import internetarchive as ia

from archive_uploader.state.store import Store
from archive_uploader.textutils import slugify


def resolve_identifier(
    base: str,
    id_hash: str,
    known_identifiers: Optional[Any] = None,
) -> str:
    """
    Resolves canonical IA item identifier. Checks known_identifiers set/store,
    local store, and remote IA status before falling back to truncated slug.
    """
    full_slug = slugify(base)
    legacy_identifier = f"flac-{full_slug}-{id_hash}"
    truncated_slug = full_slug[:50].rstrip("-")
    new_identifier = f"flac-{truncated_slug}-{id_hash}"

    # Safe check if known_identifiers is a StateStore instance
    if known_identifiers and hasattr(known_identifiers, "is_uploaded"):
        if known_identifiers.is_uploaded(legacy_identifier):
            return legacy_identifier

    # Safe check if known_identifiers is a set or iterable
    if known_identifiers and hasattr(known_identifiers, "__contains__"):
        try:
            if legacy_identifier in known_identifiers:
                return legacy_identifier
        except TypeError:
            pass

    # Fast path: Base title wasn't truncated
    if legacy_identifier == new_identifier:
        return new_identifier

    # Local state DB lookup
    try:
        store = Store()
        if store.is_uploaded(legacy_identifier):
            return legacy_identifier
    except Exception:
        pass

    # Live Internet Archive remote lookup
    try:
        item = ia.get_item(legacy_identifier)
        if getattr(item, "exists", False):
            return legacy_identifier
    except Exception:
        pass

    return new_identifier
