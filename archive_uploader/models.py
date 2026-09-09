"""
Shared data models. Kept dependency-free (no requests/mutagen imports
here) so any module can import models without dragging in IO libraries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class TrackFile:
    path: Path
    title: str = ""
    artist: str = ""
    album: str = ""
    date: str = ""
    tracknumber: str = ""
    isrc: str = ""
    composer: str = ""


@dataclass
class ExternalLink:
    """
    One badge in the description: a service's logo + a hyperlink to the
    matched page. Every enrichment provider produces zero or more of
    these instead of the description-builder hardcoding per-service ifs.
    """
    service: str          # e.g. "Qobuz", "MusicBrainz"
    url: str
    logo_url: str = ""


@dataclass
class Release:
    kind: str  # 'album' or 'single'
    dir_or_file: Path
    tracks: List[TrackFile] = field(default_factory=list)
    title: str = ""
    artist: str = ""
    date: str = ""
    source: str = "Local Tags"
    cover_url: str = ""
    cover_path: Optional[Path] = None

    # Metadata
    genre: str = ""
    label: str = ""
    upc: str = ""
    isrc: str = ""
    composer: str = ""
    copyright: str = ""
    audio_spec: str = ""
    external_description: str = ""
    wikipedia_article: str = ""

    # Provider-sourced identifiers/links, keyed by provider name
    provider_ids: Dict[str, str] = field(default_factory=dict)
    external_links: List[ExternalLink] = field(default_factory=list)
