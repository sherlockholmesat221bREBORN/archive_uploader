from __future__ import annotations

import hashlib
import json
from typing import List, Optional

from ..config import CACHE_DIR
from ..models import ExternalLink, Release
from .base import Provider
from .musicbrainz import MusicBrainzProvider
from .overrides import apply_overrides, load_overrides
from .qobuz import QobuzProvider
from .wikipedia import WikipediaProvider

DEFAULT_PROVIDERS: List[Provider] = [QobuzProvider(), MusicBrainzProvider(), WikipediaProvider()]

# Fields a provider result dict may set directly on Release (besides id/url,
# which are handled specially — see enrich()).
_MERGE_FIELDS = (
    "genre", "label", "upc", "external_description", "copyright",
    "audio_spec", "cover_url", "wikipedia_article",
)


def _release_cache_key(rel: Release) -> str:
    base = f"{rel.artist}-{rel.title}".strip() or rel.dir_or_file.name
    return hashlib.md5(base.encode("utf-8")).hexdigest()[:12]


def _cache_raw(rel: Release, provider_name: str, data: dict) -> None:
    """Write-only cache of exactly what a provider returned. Never
    hand-edited — if you want to change a fetched value, use the
    override file (enrichment/overrides.py), not this."""
    cache_dir = CACHE_DIR / _release_cache_key(rel)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{provider_name.lower()}.json").write_text(
        json.dumps(data, default=str, indent=2)
    )


def enrich(rel: Release, providers: Optional[List[Provider]] = None) -> Release:
    """
    Merge order, weakest to strongest:
      1. local FLAC tags     (already on rel, from scanning.py)
      2. provider fetches    (this function)
      3. manual overrides    (always applied last, always win)
    Re-running enrichment can never clobber a hand-written override,
    because step 3 always runs after step 2 no matter what changed.
    """
    providers = providers if providers is not None else DEFAULT_PROVIDERS
    print(f"\n[Enriching] {rel.artist} - {rel.title} ({rel.kind.upper()})")

    for provider in providers:
        try:
            result = provider.fetch(rel)
        except Exception as e:
            print(f"  ! {provider.name} provider failed: {e}")
            continue

        if not result:
            continue

        _cache_raw(rel, provider.name, result)

        if result.get("id"):
            rel.provider_ids[provider.name] = result["id"]
        if result.get("url"):
            rel.external_links.append(
                ExternalLink(service=provider.name, url=result["url"], logo_url=provider.logo_url)
            )

        for field in _MERGE_FIELDS:
            if result.get(field) and not getattr(rel, field, None):
                setattr(rel, field, result[field])

    apply_overrides(rel, load_overrides(rel))
    return rel
