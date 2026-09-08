import pytest


@pytest.fixture(autouse=True)
def _isolate_cache_dir(tmp_path, monkeypatch):
    """enrich() writes a raw-response cache keyed off the global CACHE_DIR.
    Without this, running the test suite would scatter files into the
    real ~/.config/archive_uploader/metadata_cache on whoever's machine
    runs it."""
    monkeypatch.setattr(
        "archive_uploader.enrichment.pipeline.CACHE_DIR", tmp_path / "test_metadata_cache"
    )
