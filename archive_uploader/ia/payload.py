"""Internet Archive payload and metadata builder."""

import hashlib
import tempfile
import urllib.parse
from pathlib import Path
from typing import Dict, List, Set, Tuple

from archive_uploader import __version__
from archive_uploader.ia.identifiers import resolve_identifier
from archive_uploader.models import ExternalLink, Release
from archive_uploader.packaging import create_clean_zip, derive_opus_file
from archive_uploader.state.backup import ensure_script_backup
from archive_uploader.textutils import slugify

# System files to strictly exclude from uploads
SYSTEM_EXCLUDES: Set[str] = {
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
    "@eadir",
    ".git",
    ".gitignore",
    "__pycache__",
}

# Domain to display service name mapping
DOMAIN_SERVICE_MAP: Dict[str, str] = {
    "open.qobuz.com": "Qobuz",
    "qobuz.com": "Qobuz",
    "musicbrainz.org": "MusicBrainz",
    "open.spotify.com": "Spotify",
    "spotify.com": "Spotify",
    "discogs.com": "Discogs",
    "music.apple.com": "Apple Music",
    "itunes.apple.com": "Apple Music",
    "en.wikipedia.org": "Wikipedia",
    "wikipedia.org": "Wikipedia",
    "deezer.com": "Deezer",
    "tidal.com": "Tidal",
    "bandcamp.com": "Bandcamp",
    "youtube.com": "YouTube",
    "music.youtube.com": "YouTube Music",
    "soundcloud.com": "SoundCloud",
    "allmusic.com": "AllMusic",
    "last.fm": "Last.fm",
    "amazon.com": "Amazon",
}


def render_link_badge(link: ExternalLink) -> str:
    """
    Formats an ExternalLink object into an HTML badge with fixed 16x16 icon size.
    Enforces width="16" height="16" attributes because IA's HTML sanitizer strips inline CSS style attributes.
    """
    domain = urllib.parse.urlparse(link.url).netloc.lower().replace("www.", "")
    service = link.service or DOMAIN_SERVICE_MAP.get(domain, domain.capitalize())
    logo = link.logo_url or f"https://www.google.com/s2/favicons?domain={domain}&sz=32"

    return (
        f'<a href="{link.url}" target="_blank" rel="nofollow">'
        f'<img src="{logo}" width="16" height="16" alt="{service}"> {service}</a>'
    )


def is_valid_payload_file(p: Path) -> bool:
    """Checks if a file is a valid payload asset and not a hidden OS metadata file."""
    if p.name.startswith("."):
        return False
    if p.name.lower() in SYSTEM_EXCLUDES:
        return False
    return True


def determine_file_key(file_path: Path, rel: Release) -> str:
    """
    Determines relative IA file key, preserving folder structure for multi-file items
    and multi-disc subdirectories.
    """
    if rel.kind != "album" or not rel.dir_or_file.is_dir():
        return file_path.name

    album_dir = rel.dir_or_file
    try:
        rel_parts = file_path.relative_to(album_dir).parts
        if len(rel_parts) > 1:
            return file_path.relative_to(album_dir).as_posix()
    except ValueError:
        pass

    return file_path.name


def build_ia_payload(
    rel: Release,
    collection: str,
    mediatype: str,
    opus_bitrate: str = "192k",
) -> Tuple[str, dict, Dict[str, str], List[Path]]:
    """
    Builds Internet Archive item payload:
      1. Resolves canonical identifier.
      2. Creates version backup for code recoverability.
      3. Transcodes deterministic Opus files.
      4. Builds deterministic FLAC and Opus ZIP archives (for albums).
      5. Generates clean HTML description with 16x16 icon badges.
      6. Assembles metadata dictionary and external-identifier URNs.
      7. Maps local files to IA item destination keys.
    """
    base = f"{rel.artist} {rel.title}".strip() or rel.dir_or_file.name
    id_hash = hashlib.md5(base.encode("utf-8")).hexdigest()[:8]
    identifier = resolve_identifier(base, id_hash)

    # Ensure self-backup snapshot for source script recoverability
    backup_path, script_hash = ensure_script_backup()

    temp_cleanup_files: List[Path] = []
    opus_map: Dict[Path, Path] = {}

    # Gather source FLAC files
    flac_list = [t.path for t in rel.tracks if t.path and t.path.exists()]
    if not flac_list and rel.dir_or_file.is_file():
        flac_list = [rel.dir_or_file]
    elif not flac_list and rel.dir_or_file.is_dir():
        flac_list = sorted([
            p for p in rel.dir_or_file.rglob("*.flac")
            if is_valid_payload_file(p)
        ])

    print(f"   🎵 Deriving deterministic {opus_bitrate} Opus audio files...")
    for flac_p in flac_list:
        try:
            opus_p = derive_opus_file(flac_p, bitrate=opus_bitrate)
            opus_map[flac_p] = opus_p
            temp_cleanup_files.append(opus_p)
        except Exception as e:
            print(f"  ! Error deriving Opus for {flac_p.name}: {e}")

    # Determine single vs album status
    is_single = (
        rel.kind == "single"
        or getattr(rel, "is_single", False)
        or "(SINGLE)" in rel.title.upper()
        or " - SINGLE" in rel.title.upper()
        or len(flac_list) <= 1
    )

    # HTML Description Construction
    desc: List[str] = [f"<b>{rel.title}</b> by <b>{rel.artist}</b><br><br>"]

    if rel.date:
        desc.append(f"<b>Release Date:</b> {rel.date}<br>")
    if rel.genre:
        desc.append(f"<b>Genre:</b> {rel.genre}<br>")
    if rel.label:
        desc.append(f"<b>Label / Publisher:</b> {rel.label}<br>")
    if rel.upc:
        desc.append(f"<b>UPC / Barcode:</b> {rel.upc}<br>")
    if rel.isrc:
        desc.append(f"<b>ISRC:</b> {rel.isrc}<br>")
    if rel.audio_spec:
        desc.append(f"<b>Format:</b> FLAC Lossless ({rel.audio_spec})<br>")
    if rel.composer:
        desc.append(f"<b>Composer:</b> {rel.composer}<br>")
    if rel.copyright:
        desc.append(f"<b>Copyright:</b> {rel.copyright}<br>")
    if getattr(rel, "source", None) and rel.source != "Local Tags":
        desc.append(f"<b>Source:</b> {rel.source}<br>")

    files_dict: Dict[str, str] = {}

    slug_name = slugify(base)
    flac_zip_name = f"{slug_name}-flac-complete.zip"
    opus_zip_name = f"{slug_name}-opus-complete.zip"

    if not is_single:
        temp_zip_dir = Path(tempfile.gettempdir()) / "archive_uploader_zips"
        temp_zip_dir.mkdir(exist_ok=True)

        flac_zip_path = temp_zip_dir / flac_zip_name
        opus_zip_path = temp_zip_dir / opus_zip_name

        print("   📦 Packaging deterministic FLAC and Opus ZIP structures...")
        create_clean_zip(rel, flac_zip_path, exclude_ext=".opus", opus_map=opus_map)
        create_clean_zip(rel, opus_zip_path, exclude_ext=".flac", opus_map=opus_map)

        temp_cleanup_files.extend([flac_zip_path, opus_zip_path])

        desc.append("<br><b>Direct Custom Downloads (Complete Folders &amp; Artwork):</b><br>")
        desc.append(
            f'• <a href="https://archive.org/download/{identifier}/{flac_zip_name}">Download Full Album (FLAC Lossless + Docs)</a><br>'
        )
        desc.append(
            f'• <a href="https://archive.org/download/{identifier}/{opus_zip_name}">Download Full Album ({opus_bitrate} Opus + Docs)</a><br>'
        )

        files_dict[flac_zip_name] = str(flac_zip_path)
        files_dict[opus_zip_name] = str(opus_zip_path)
    else:
        print("   ℹ️  Single detected: Skipping FLAC/Opus ZIP archive creation.")

    if rel.kind == "album" and rel.tracks and not is_single:
        desc.append("<br><b>Tracklist:</b><br><ol>")
        for t in rel.tracks:
            track_str = t.title
            if t.artist and t.artist.lower() != rel.artist.lower():
                track_str += f" - {t.artist}"
            if t.composer:
                track_str += f" (Comp. {t.composer})"
            desc.append(f"<li>{track_str}</li>")
        desc.append("</ol>")

    if rel.external_description:
        desc.append(f"<br><b>Album Description:</b><br>{rel.external_description}<br>")

    if rel.wikipedia_article:
        desc.append(f"<br><b>Article Summary:</b><br>{rel.wikipedia_article}<br>")

    if rel.external_links:
        badges = [render_link_badge(link) for link in rel.external_links]
        desc.append("<br><b>External Links:</b><br>" + " | ".join(badges))

    # Include source script backup file for full code recoverability
    if backup_path.exists():
        backup_key = f"uploader_script_v{__version__}_{script_hash[:8]}{backup_path.suffix}"
        files_dict[backup_key] = str(backup_path)

    # Map individual FLAC files
    for flac_p in flac_list:
        key = determine_file_key(flac_p, rel)
        files_dict[key] = str(flac_p)

    # Map individual derived Opus files
    for flac_p, opus_p in opus_map.items():
        if opus_p.exists():
            key = determine_file_key(opus_p, rel)
            files_dict[key] = str(opus_p)

    # Map ancillary files (booklets, PDFs, CUEs, artwork, extra documentation)
    if rel.kind == "album" and rel.dir_or_file.is_dir():
        for extra in rel.dir_or_file.rglob("*"):
            if extra.is_file() and is_valid_payload_file(extra):
                if extra.suffix.lower() not in (".flac", ".opus"):
                    key = determine_file_key(extra, rel)
                    if key not in files_dict:
                        files_dict[key] = str(extra)

    # Map Cover Image
    if rel.cover_path and rel.cover_path.exists():
        ext = rel.cover_path.suffix.lower()
        cover_key = f"cover{ext}"
        if cover_key not in files_dict and rel.cover_path.name not in files_dict:
            files_dict[cover_key] = str(rel.cover_path)

    # Build external identifier URN list
    ext_ids: List[str] = []
    for pid, val in rel.provider_ids.items():
        if val:
            ext_ids.append(f"urn:{pid}:{val}")
    if rel.upc:
        ext_ids.append(f"urn:upc:{rel.upc}")
    if rel.isrc:
        ext_ids.append(f"urn:isrc:{rel.isrc}")

    # Build metadata dictionary for Internet Archive API
    subject_tags = [
        t for t in ["flac", "lossless audio", rel.artist, rel.genre, rel.label] if t
    ]

    metadata: Dict[str, any] = {
        "title": rel.title,
        "creator": rel.artist,
        "mediatype": mediatype,
        "collection": collection,
        "date": rel.date or "",
        "description": "".join(desc),
        "subject": subject_tags,
        "uploader_version": f"archive_uploader v{__version__}",
        "uploader_script_sha256": script_hash,
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
    if rel.composer:
        metadata["composer"] = rel.composer

    if ext_ids:
        metadata["external-identifier"] = sorted(list(set(ext_ids)))
    if rel.external_links:
        metadata["external_link"] = sorted(list(set(link.url for link in rel.external_links)))

    return identifier, metadata, files_dict, temp_cleanup_files
