from archive_uploader.state.log_store import LogStateStore


def test_mark_uploaded_writes_only_to_its_own_device_log(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    store_a = LogStateStore(logs_dir=logs_dir, device_id="device-a")
    store_a.mark_uploaded("flac-example-a-deadbeef", files=["a.flac"])

    assert (logs_dir / "device-a.ndjson").exists()
    assert not (logs_dir / "device-b.ndjson").exists()


def test_all_uploaded_merges_across_every_device_log(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    LogStateStore(logs_dir=logs_dir, device_id="device-a").mark_uploaded("id-from-a", files=["a.flac"])
    LogStateStore(logs_dir=logs_dir, device_id="device-b").mark_uploaded("id-from-b", files=["b.flac"])

    merged = LogStateStore(logs_dir=logs_dir, device_id="device-a")
    assert merged.all_uploaded() == {"id-from-a", "id-from-b"}
    assert merged.is_uploaded("id-from-b")  # can see the other device's writes


def test_a_torn_or_corrupt_line_is_skipped_not_fatal(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    log_file = logs_dir / "device-a.ndjson"
    log_file.write_text(
        '{"event": "uploaded", "identifier": "good-one", "files": [], "ts": 1}\n'
        '{"event": "uploaded", "identifier": "torn-wri\n'  # simulated crash mid-write
    )

    store = LogStateStore(logs_dir=logs_dir, device_id="device-a")
    assert store.all_uploaded() == {"good-one"}


def test_missing_logs_dir_behaves_like_empty_state(tmp_path):
    store = LogStateStore(logs_dir=tmp_path / "does_not_exist_yet", device_id="device-a")
    assert store.all_uploaded() == set()
    assert store.is_uploaded("anything") is False
