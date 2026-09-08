from pathlib import Path

from archive_uploader.models import Release
from archive_uploader.packaging import determine_file_key


def _album_release(album_dir: Path) -> Release:
    return Release(kind="album", dir_or_file=album_dir)


def test_single_disc_album_flattens_to_filename(tmp_path):
    album_dir = tmp_path / "Some Album"
    album_dir.mkdir()
    (album_dir / "01 - Track One.flac").write_bytes(b"")
    (album_dir / "02 - Track Two.flac").write_bytes(b"")
    (album_dir / "cover.jpg").write_bytes(b"")

    rel = _album_release(album_dir)
    key = determine_file_key(album_dir / "01 - Track One.flac", rel)

    assert key == "01 - Track One.flac"


def test_multi_disc_album_preserves_disc_subpath(tmp_path):
    album_dir = tmp_path / "Some Album"
    (album_dir / "CD 01").mkdir(parents=True)
    (album_dir / "CD 02").mkdir(parents=True)
    (album_dir / "CD 01" / "01 - Track One.flac").write_bytes(b"")
    (album_dir / "CD 02" / "01 - Track One.flac").write_bytes(b"")

    rel = _album_release(album_dir)
    key = determine_file_key(album_dir / "CD 01" / "01 - Track One.flac", rel)

    assert key == "CD 01/01 - Track One.flac"


def test_single_release_kind_returns_bare_filename(tmp_path):
    flac_file = tmp_path / "Track.flac"
    flac_file.write_bytes(b"")
    rel = Release(kind="single", dir_or_file=flac_file)

    assert determine_file_key(flac_file, rel) == "Track.flac"


def test_hidden_and_system_files_do_not_count_as_a_second_disc(tmp_path):
    # A lone .DS_Store-style subdir shouldn't make a single-disc album
    # look multi-disc and start emitting subpaths for everything.
    album_dir = tmp_path / "Some Album"
    album_dir.mkdir()
    (album_dir / "01 - Track One.flac").write_bytes(b"")
    hidden_dir = album_dir / ".some_hidden_dir"
    hidden_dir.mkdir()
    (hidden_dir / "junk").write_bytes(b"")

    rel = _album_release(album_dir)
    key = determine_file_key(album_dir / "01 - Track One.flac", rel)

    assert key == "01 - Track One.flac"
