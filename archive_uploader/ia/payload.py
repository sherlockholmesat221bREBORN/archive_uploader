from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Set, Tuple

from ..config import TEMP_DIR, is_valid_asset
from ..models import Release
from ..packaging import create_clean_zip, derive_opus_file, determine_file_key
from ..textutils import slugify
from .identifiers import resolve_identifier


def _render_link_badges(rel: Release) -> str:
    """
    Generic badge renderer: logo + hyperlink per matched provider.
    Add a new Provider and its badge shows up here automatically —
    nothing in this function needs to change.
    """
    if not rel.external_links:
        return ""
    parts = []
    for link in rel.external_links:
        logo = (
            f'<img src="{link.logo_url}" height="16" '
            f'style="vertical-align:middle;margin-right:4px;">'
            if link.logo_url
            else ""
        )
        parts.append(f'<a href="{link.url}" target="_blank" rel="nofollow">{logo}{link.service}</a>')
    return "<br><b>External Links:</b><br>" + " | ".join(parts) + "<br>"


def build_description(rel: Release, flac_zip_name: str, opus_zip_name: str, identifier: str) -> str:
    desc = [f"<b>{rel.title}</b> by <b>{rel.artist}</b><br><br>"]
    if rel.date:
        desc.append(f"<b>Release Date:</b> {rel.date}<br>")
    if rel.genre:
        desc.append(f"<b>Genre:</b> {rel.genre}<br>")
    if rel.label:
        desc.append(f"<b>Label / Publisher:</b> {rel.label}<br>")
    if rel.upc:
        desc.append(f"<b>UPC / Barcode:</b> {rel.upc}<br>")
    if rel.audio_spec:
        desc.append(f"<b>Format:</b> FLAC Lossless ({rel.audio_spec})<br>")
    if rel.copyright:
        desc.append(f"<b>Copyright:</b> {rel.copyright}<br>")

    desc.append("<br><b>Direct Custom Downloads (Complete Folders & Artwork):</b><br>")
    desc.append(
        f'\u2022 <a href="https://archive.org/download/{identifier}/{flac_zip_name}">'
        f"Download Full Album (FLAC Lossless + Docs)</a><br>"
    )
    desc.append(
        f'\u2022 <a href="https://archive.org/download/{identifier}/{opus_zip_name}">'
        f"Download Full Album (128kbps Opus + Docs)</a><br>"
    )

    if rel.kind == "album" and rel.tracks:
        desc.append("<br><b>Tracklist:</b><br><ol>")
        for t in rel.tracks:
            desc.append(f"<li>{t.title}</li>")
        desc.append("</ol>")

    if rel.external_description:
        desc.append(f"<br><b>Qobuz Commentary:</b><br>{rel.external_description}<br>")

    if rel.wikipedia_article:
        desc.append(f"<br><b>Article Summary:</b><br>{rel.wikipedia_article}<br>")

    desc.append(_render_link_badges(rel))

    return "".join(desc)


def build_metadata(rel: Release, collection: str, mediatype: str, description: str) -> dict:
    metadata: dict = {
        "title": rel.title,
        "creator": rel.artist,
        "mediatype": mediatype,
        "collection": collection,
        "date": rel.date or "",
        "description": description,
        "subject": [t for t in ["flac", "lossless audio", rel.artist, rel.genre, rel.label] if t],
    }

    if rel.upc:
        metadata["upc"] = rel.upc
        metadata["barcode"] = rel.upc
    if rel.genre:
        metadata["genre"] = rel.genre
    if rel.label:
        metadata["publisher"] = rel.label
    if rel.isrc:
        metadata["isrc"] = rel.isrc

    # Generic, provider-agnostic identifier export — was previously
    # hardcoded per-service (musicbrainz_release_id / qobuz_id). Now any
    # provider that sets "id" shows up here as "<name-lower>_id" and in
    # external-identifier automatically.
    ext_ids = [f"urn:{name.lower()}_id:{pid}" for name, pid in rel.provider_ids.items()]
    if rel.upc:
        ext_ids.append(f"urn:upc:{rel.upc}")
    if ext_ids:
        metadata["external-identifier"] = ext_ids

    for name, pid in rel.provider_ids.items():
        metadata[f"{name.lower()}_id"] = pid

    ext_links = [link.url for link in rel.external_links if link.url]
    if ext_links:
        metadata["external_link"] = ext_links

    return metadata


def build_ia_payload(
    rel: Release, collection: str, mediatype: str, known_identifiers: Set[str]
) -> Tuple[str, dict, Dict[str, str], List[Path]]:
    base = f"{rel.artist} {rel.title}".strip() or rel.dir_or_file.name
    id_hash = hashlib.md5(base.encode("utf-8")).hexdigest()[:8]
    identifier = resolve_identifier(base, id_hash, known_identifiers)

    temp_cleanup_files: List[Path] = []
    opus_map: Dict[Path, Path] = {}

    print("   \U0001f3b5 Deriving 128 kbps Opus audio files...")
    for t in rel.tracks:
        try:
            opus_p = derive_opus_file(t.path, bitrate="128k")
            opus_map[t.path] = opus_p
            temp_cleanup_files.append(opus_p)
        except Exception as e:
            print(f"  ! Error deriving Opus for {t.path.name}: {e}")

    zip_dir = TEMP_DIR / "zips"
    zip_dir.mkdir(exist_ok=True)

    slug_name = slugify(base)
    flac_zip_name = f"{slug_name}-flac-complete.zip"
    opus_zip_name = f"{slug_name}-opus-complete.zip"
    flac_zip_path = zip_dir / flac_zip_name
    opus_zip_path = zip_dir / opus_zip_name

    print("   \U0001f4e6 Packaging complete FLAC and Opus ZIP structures...")
    create_clean_zip(rel, flac_zip_path, exclude_ext=".opus", opus_map=opus_map)
    create_clean_zip(rel, opus_zip_path, exclude_ext=".flac", opus_map=opus_map)
    temp_cleanup_files.extend([flac_zip_path, opus_zip_path])

    description = build_description(rel, flac_zip_name, opus_zip_name, identifier)
    metadata = build_metadata(rel, collection, mediatype, description)

    files_dict: Dict[str, str] = {}
    if rel.kind == "album":
        for file_path in rel.dir_or_file.rglob("*"):
            if file_path.is_file() and is_valid_asset(file_path):
                key = determine_file_key(file_path, rel)
                files_dict[key] = str(file_path)
    else:
        for t in rel.tracks:
            files_dict[t.path.name] = str(t.path)
            if t.path in opus_map:
                op = opus_map[t.path]
                files_dict[op.name] = str(op)

    files_dict[flac_zip_name] = str(flac_zip_path)
    files_dict[opus_zip_name] = str(opus_zip_path)

    if rel.cover_path and rel.cover_path.exists():
        if str(rel.cover_path) not in files_dict.values():
            ext = rel.cover_path.suffix.lower()
            files_dict[f"cover{ext}"] = str(rel.cover_path)

    return identifier, metadata, files_dict, temp_cleanup_files
