"""
Turns a folder tree into Release objects, reading only local FLAC tags
and local cover art. No network calls happen in this module — that's
enrichment's job (see enrichment/pipeline.py).
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from mutagen.flac import FLAC

from .config import TEMP_DIR, is_valid_asset
from .models import Release, TrackFile
from .textutils import slugify


def read_flac_tags(path: Path) -> Tuple[TrackFile, dict]:
    tf = TrackFile(path=path)
    raw_meta: dict = {}
    try:
        audio = FLAC(str(path))
        tf.title = audio.get("title", [""])[0]
        tf.artist = audio.get("artist", [""])[0]
        tf.album = audio.get("album", [""])[0]
        tf.date = audio.get("date", [""])[0]
        tf.tracknumber = audio.get("tracknumber", [""])[0]
        tf.isrc = audio.get("isrc", [""])[0]
        tf.composer = audio.get("composer", [""])[0]

        raw_meta["upc"] = audio.get("upc", audio.get("barcode", [""]))[0]
        raw_meta["genre"] = audio.get("genre", [""])[0]
        raw_meta["copyright"] = audio.get("copyright", [""])[0]

        publisher = audio.get(
            "organization", audio.get("performer:musicpublisher", audio.get("publisher", [""]))
        )[0]
        raw_meta["label"] = publisher
    except Exception as e:
        print(f"  ! Error reading tags from {path.name}: {e}")
    return tf, raw_meta


def extract_embedded_cover(flac_path: Path, output_dir: Path, slug_name: str) -> Optional[Path]:
    try:
        audio = FLAC(str(flac_path))
        if audio.pictures:
            pic = audio.pictures[0]
            ext = ".png" if "png" in pic.mime.lower() else ".jpg"
            out_path = output_dir / f"{slug_name}_cover{ext}"
            with open(out_path, "wb") as f:
                f.write(pic.data)
            return out_path
    except Exception:
        pass
    return None


def detect_cover(rel: Release) -> None:
    if rel.kind == "album":
        for name in ["cover.jpg", "cover.png", "folder.jpg", "folder.png", "front.jpg"]:
            p = rel.dir_or_file / name
            if p.exists():
                rel.cover_path = p
                return

    covers_dir = TEMP_DIR / "covers"
    covers_dir.mkdir(exist_ok=True)
    slug = slugify(f"{rel.artist}-{rel.title}")

    if rel.tracks:
        extracted = extract_embedded_cover(rel.tracks[0].path, covers_dir, slug)
        if extracted:
            rel.cover_path = extracted


def _build_album_release(entry: Path) -> Optional[Release]:
    flacs = sorted(entry.rglob("*.flac"))
    if not flacs:
        return None

    tracks: List[TrackFile] = []
    album_meta: dict = {}
    for f in flacs:
        tf, meta = read_flac_tags(f)
        tracks.append(tf)
        if not album_meta:
            album_meta = meta

    tracks.sort(key=lambda t: int(re.sub(r"\D", "", t.tracknumber or "0") or 0))

    rel = Release(kind="album", dir_or_file=entry, tracks=tracks)
    rel.artist = tracks[0].artist or "Unknown Artist"
    rel.title = tracks[0].album or entry.name
    rel.date = tracks[0].date
    rel.upc = album_meta.get("upc", "")
    rel.genre = album_meta.get("genre", "")
    rel.label = album_meta.get("label", "")
    rel.copyright = album_meta.get("copyright", "")
    rel.isrc = tracks[0].isrc
    rel.composer = tracks[0].composer

    detect_cover(rel)
    return rel


def _build_single_release(entry: Path) -> Release:
    tf, meta = read_flac_tags(entry)
    rel = Release(kind="single", dir_or_file=entry, tracks=[tf])
    rel.artist = tf.artist or "Unknown Artist"
    rel.title = tf.title or entry.stem
    rel.date = tf.date
    rel.upc = meta.get("upc", "")
    rel.genre = meta.get("genre", "")
    rel.label = meta.get("label", "")
    rel.copyright = meta.get("copyright", "")
    rel.isrc = tf.isrc
    rel.composer = tf.composer

    detect_cover(rel)
    return rel


def scan_directory(root: Path) -> List[Release]:
    releases: List[Release] = []

    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            rel = _build_album_release(entry)
            if rel:
                releases.append(rel)

    for entry in sorted(root.glob("*.flac")):
        releases.append(_build_single_release(entry))

    return releases


__all__ = [
    "read_flac_tags",
    "extract_embedded_cover",
    "detect_cover",
    "scan_directory",
    "is_valid_asset",  # re-exported for convenience; canonical home is config.py
]
