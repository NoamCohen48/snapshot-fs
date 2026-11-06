from datetime import UTC, datetime, timedelta

import pytest

from snapshotfs.cli import main
from snapshotfs.parser import WindowsDirParser
from snapshotfs.source import FileSource
from snapshotfs.store import ImportFailure
from snapshotfs.store.memory import create_memory_store
from snapshotfs.store.sqlite import create_sqlite_store, open_sqlite_store
from snapshotfs.timestamps import localize, source_zone


def test_named_zone_roundtrips_in_portable_artifact(listing_file, tmp_path):
    artifact = tmp_path / "zoned.db"
    parser = WindowsDirParser(source_timezone="Asia/Jerusalem")
    with create_sqlite_store(FileSource(listing_file), parser, artifact):
        pass
    with open_sqlite_store(artifact) as store:
        file = next(
            node
            for node in store.iter_nodes()
            if node.mounted_name == b"notes file.txt"
        )
        assert file.modified_at.utcoffset() == timedelta(hours=2)
        assert file.modified_at.astimezone(UTC) == datetime(
            2024, 1, 2, 13, 5, tzinfo=UTC
        )
        metadata = store.get_snapshot(file.snapshot_id).source_metadata
        assert metadata["source_timezone"] == "Asia/Jerusalem"


@pytest.mark.parametrize(("month", "offset"), [(1, -5), (7, -4)])
def test_zone_uses_timestamp_date_not_current_offset(month, offset):
    value = localize(datetime(2024, month, 15, 12), source_zone("America/New_York"))
    assert value.utcoffset() == timedelta(hours=offset)


def test_dst_gap_and_fold_require_explicit_resolution():
    zone = source_zone("America/New_York")
    with pytest.raises(ValueError, match="nonexistent"):
        localize(datetime(2024, 3, 10, 2, 30), zone)
    repeated = datetime(2024, 11, 3, 1, 30)
    with pytest.raises(ValueError, match="ambiguous"):
        localize(repeated, zone)
    earlier = localize(repeated, zone, "earlier").astimezone(UTC)
    later = localize(repeated, zone, "later").astimezone(UTC)
    assert later - earlier == timedelta(hours=1)


def test_dst_failure_rejects_both_backends_atomically(listing_file, tmp_path):
    text = listing_file.read_text().replace(
        "01/02/2024  03:05 PM", "03/10/2024  02:30 AM"
    )
    listing_file.write_text(text, encoding="utf-8")
    parser = WindowsDirParser(source_timezone="America/New_York")
    for backend in ("memory", "sqlite"):
        with pytest.raises(ImportFailure) as caught:
            if backend == "memory":
                create_memory_store(FileSource(listing_file), parser)
            else:
                create_sqlite_store(
                    FileSource(listing_file), parser, tmp_path / "invalid.db"
                )
        assert any(
            item.code == "INVALID_LOCAL_TIME" for item in caught.value.diagnostics
        )
    assert not (tmp_path / "invalid.db").exists()


def test_invalid_timezone_is_a_usage_error(listing_file, tmp_path, capsys):
    assert (
        main(
            [
                "sqlite",
                "create",
                str(tmp_path / "out.db"),
                "--source",
                "file",
                str(listing_file),
                "--parser",
                "windows-dir",
                "--source-timezone",
                "Bad/Timezone",
            ]
        )
        == 2
    )
    assert "unknown source timezone" in capsys.readouterr().err
