from __future__ import annotations

from typing import Set

import internetarchive as ia

from ..textutils import slugify


def resolve_identifier(base: str, id_hash: str, known_identifiers: Set[str]) -> str:
    """
    Two identifier schemes have existed over time (untruncated slug,
    then a 50-char-truncated slug). This picks the right one so old
    items keep resuming under their original id instead of forking
    into a duplicate upload. Don't "simplify" this to just the new
    scheme — see DECISIONS.md.
    """
    full_slug = slugify(base)
    legacy_identifier = f"flac-{full_slug}-{id_hash}"
    truncated_slug = full_slug[:50].rstrip("-")
    new_identifier = f"flac-{truncated_slug}-{id_hash}"

    if legacy_identifier in known_identifiers:
        return legacy_identifier

    if legacy_identifier != new_identifier:
        try:
            if ia.get_item(legacy_identifier).exists:
                print(f"  -> [LEGACY MATCH] Resuming using original ID: {legacy_identifier}")
                return legacy_identifier
        except Exception:
            pass

    return new_identifier
