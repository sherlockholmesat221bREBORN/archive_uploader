from unittest.mock import MagicMock, patch

from archive_uploader.ia.identifiers import resolve_identifier

LONG_BASE = "A" * 80  # forces slug truncation, so legacy_identifier != new_identifier
SHORT_BASE = "Short Title"


def test_known_legacy_identifier_is_reused_without_network_call():
    legacy = f"flac-{'a' * 80}-deadbeef"
    with patch("archive_uploader.ia.identifiers.ia.get_item") as mock_get_item:
        result = resolve_identifier(LONG_BASE, "deadbeef", known_identifiers={legacy})
    assert result == legacy
    mock_get_item.assert_not_called()


def test_short_base_never_needs_a_network_check():
    # legacy == new identifier when there's no truncation, so the
    # legacy-lookup branch should be skipped entirely.
    with patch("archive_uploader.ia.identifiers.ia.get_item") as mock_get_item:
        resolve_identifier(SHORT_BASE, "deadbeef", known_identifiers=set())
    mock_get_item.assert_not_called()


def test_falls_back_to_legacy_id_when_it_exists_remotely():
    mock_item = MagicMock()
    mock_item.exists = True
    with patch("archive_uploader.ia.identifiers.ia.get_item", return_value=mock_item):
        result = resolve_identifier(LONG_BASE, "deadbeef", known_identifiers=set())
    assert result.startswith("flac-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert result.endswith("-deadbeef")
    assert len(result) > len(f"flac-{'a' * 50}-deadbeef")  # untruncated


def test_uses_new_truncated_id_when_legacy_does_not_exist_remotely():
    mock_item = MagicMock()
    mock_item.exists = False
    with patch("archive_uploader.ia.identifiers.ia.get_item", return_value=mock_item):
        result = resolve_identifier(LONG_BASE, "deadbeef", known_identifiers=set())
    assert result == f"flac-{'a' * 50}-deadbeef"


def test_uses_new_truncated_id_when_legacy_lookup_raises():
    with patch("archive_uploader.ia.identifiers.ia.get_item", side_effect=Exception("network down")):
        result = resolve_identifier(LONG_BASE, "deadbeef", known_identifiers=set())
    assert result == f"flac-{'a' * 50}-deadbeef"
