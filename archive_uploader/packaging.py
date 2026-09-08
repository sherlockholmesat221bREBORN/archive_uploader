"""
Everything that turns a Release's files into upload-ready artifacts:
128k Opus transcodes and the two "complete folder" ZIPs. Deliberately
has no knowledge of Internet Archive — ia/payload.py wires this in.
"""
from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Dict

from .config import is_valid_asset
from .models import Release


def derive_opus_file(flac_path: Path, bitrate: str = "128k") -> Path:
    """Encodes FLAC to Opus using opusenc, preserving all tags and covers natively."""
    opus_path = flac_path.with_suffix(".opus")

    if not opus_path.exists() or opus_path.stat().st_size == 0:
        kbps = bitrate.replace("k", "")  # opusenc wants a bare integer
        cmd = ["opusenc", "--quiet", "--bitrate", kbps, str(flac_path), str(opus_path)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"  ! opusenc Error for {flac_path.name}:\n{e.stderr}")
            if opus_path.exists():
                opus_path.unlink()  # clean up partial/0-byte files
            raise

    return opus_path


def determine_file_key(file_path: Path, rel: Release) -> str:
    """
    Flattens a single-disc album to root filenames, preserves 'CD 01/'
    style subpaths for genuine multi-disc releases. This is exactly the
    kind of small, easy-to-shrug-off logic that's actually load-bearing
    — see tests/test_packaging.py.
    """
    if rel.kind != "album":
        return file_path.name

    album_dir = rel.dir_or_file
    all_files = [f for f in album_dir.rglob("*") if f.is_file() and is_valid_asset(f)]

    subdirs = {
        f.relative_to(album_dir).parts[0]
        for f in all_files
        if len(f.relative_to(album_dir).parts) > 1
    }

    if len(subdirs) <= 1:
        return file_path.name

    return file_path.relative_to(album_dir).as_posix()


def create_clean_zip(rel: Release, zip_path: Path, exclude_ext: str, opus_map: Dict[Path, Path]):
    """Creates a ZIP file preserving exact folder structure, filtering out one extension."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if rel.kind == "album":
            album_dir = rel.dir_or_file
            for file_path in album_dir.rglob("*"):
                if not file_path.is_file() or not is_valid_asset(file_path):
                    continue

                ext = file_path.suffix.lower()
                if ext == exclude_ext:
                    continue

                rel_posix = file_path.relative_to(album_dir)

                if exclude_ext == ".flac" and ext == ".opus":
                    zf.write(file_path, arcname=rel_posix.as_posix())
                elif exclude_ext == ".opus" and ext == ".flac":
                    zf.write(file_path, arcname=rel_posix.as_posix())
                elif ext not in (".flac", ".opus"):
                    zf.write(file_path, arcname=rel_posix.as_posix())
        else:
            flac_file = rel.tracks[0].path
            if exclude_ext == ".opus":
                zf.write(flac_file, arcname=flac_file.name)
            elif exclude_ext == ".flac" and flac_file in opus_map:
                opus_file = opus_map[flac_file]
                zf.write(opus_file, arcname=opus_file.name)

            if rel.cover_path and rel.cover_path.exists():
                zf.write(rel.cover_path, arcname=rel.cover_path.name)


def delete_local_release(rel: Release):
    """Safely deletes local files/folders — only ever called after verified upload."""
    try:
        if rel.kind == "album" and rel.dir_or_file.is_dir():
            shutil.rmtree(rel.dir_or_file)
            print(f"   \U0001f5d1  Deleted complete local album directory: {rel.dir_or_file}")
        elif rel.dir_or_file.is_file():
            rel.dir_or_file.unlink()
            print(f"   \U0001f5d1  Deleted local single file: {rel.dir_or_file}")
    except Exception as e:
        print(f"  ! Failed to delete local files for '{rel.title}': {e}")
