import io
import sqlite3
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import BinaryIO

import pytest

import snapshotfs.api as api
from snapshotfs.cli import main
from snapshotfs.diagnostics import DiagnosticCollector, ImportDiagnostic, Severity
from snapshotfs.import_service import ImportFailure, create_sqlite_store
from snapshotfs.model import NodeKind, Observation, ParsedEntry, Snapshot
from snapshotfs.parsers.base import ParseResult
from snapshotfs.parsers.windows_dir.paths import to_mounted_path
from snapshotfs.stores.memory import BuildError, InMemorySnapshotBuilder
from snapshotfs.stores.sqlite import (
    SQLiteDestinationExistsError,
    SQLiteSchemaError,
    SQLiteSnapshotBuilder,
    SQLiteStoreClosedError,
    SQLiteStoreError,
    open_sqlite_store,
)


class MemorySource:
    uri = "memory:sqlite-test"
    size = 0

    def open(self) -> AbstractContextManager[BinaryIO]:
        return nullcontext(io.BytesIO())


class EntriesParser:
    format_name = "entries"

    def __init__(
        self,
        entries: list[ParsedEntry],
        diagnostics: tuple[ImportDiagnostic, ...] = (),
        *,
        fail: bool = False,
    ) -> None:
        self._entries = entries
        self._diagnostics = diagnostics
        self._fail = fail

    def parse(self, stream: BinaryIO) -> ParseResult:
        del stream
        collector = DiagnosticCollector()

        def entries():
            for item in self._diagnostics:
                collector.add(item)
            yield from self._entries
            if self._fail:
                raise RuntimeError("parser failed")

        return ParseResult(entries(), collector)


def entry(
    path: str | tuple[str, ...],
    kind: NodeKind = NodeKind.DIRECTORY,
    observation: Observation = Observation.SECTION_HEADER,
    size: int | None = None,
    line: int = 1,
    content: bytes | None = None,
    metadata: dict[str, object] | None = None,
) -> ParsedEntry:
    return ParsedEntry(
        to_mounted_path(PureWindowsPath(path)) if isinstance(path, str) else path,
        kind,
        observation,
        size,
        datetime(2024, 2, 3, 4, 5)
        if observation is not Observation.SECTION_HEADER
        else None,
        line,
        content,
        metadata or {},
    )


def sample_entries() -> list[ParsedEntry]:
    return [
        entry(
            r"c:\Folder\z.txt",
            NodeKind.FILE,
            Observation.FILE_ENTRY,
            3,
            1,
            b"\x00x\xff",
            {"label": "caf\u00e9", "nested": [1, True, None]},
        ),
        entry(r"C:\Folder\a.txt", NodeKind.FILE, Observation.FILE_ENTRY, 0, 2),
        entry(r"C:\Folder", NodeKind.DIRECTORY, Observation.DIRECTORY_ENTRY, line=3),
    ]


def test_builder_parity_roundtrip_metadata_content_and_offsets(tmp_path: Path) -> None:
    snapshot = Snapshot(
        "snapshot",
        "memory:test",
        "test",
        datetime(2024, 1, 1, tzinfo=UTC),
        {"host": "\u00e9"},
    )
    memory_builder = InMemorySnapshotBuilder(snapshot)
    sqlite_builder = SQLiteSnapshotBuilder(snapshot, tmp_path / "snapshot.db")
    for parsed in sample_entries():
        memory_builder.add(parsed)
        sqlite_builder.add(parsed)
    diagnostic = ImportDiagnostic(Severity.WARNING, "TEST", "retained", 9)
    memory = memory_builder.finish((diagnostic,), 7)
    sqlite_store = sqlite_builder.finish((diagnostic,), 7)
    try:
        assert list(sqlite_store.iter_nodes()) == list(memory.iter_nodes())
        assert sqlite_store.get_snapshot("snapshot") == memory.get_snapshot("snapshot")
        assert sqlite_store.diagnostics == (diagnostic,)
        assert sqlite_store.diagnostic_count == 7
        drive = sqlite_store.lookup(1, b"C")
        assert drive is not None
        folder = sqlite_store.lookup(drive.id, b"Folder")
        assert folder is not None
        assert [
            node.mounted_name for node in sqlite_store.iter_children(folder.id)
        ] == [
            b"a.txt",
            b"z.txt",
        ]
        assert [
            node.mounted_name for node in sqlite_store.iter_children(folder.id, 1)
        ] == [b"z.txt"]
        assert sqlite_store.lookup(folder.id, b"z.txt").content == b"\x00x\xff"  # type: ignore[union-attr]
    finally:
        sqlite_store.close()

    with open_sqlite_store(tmp_path / "snapshot.db") as reopened:
        assert reopened.get_snapshot("snapshot").source_metadata == {"host": "\u00e9"}
        assert reopened.get_root("snapshot").id == 1


def test_generic_relative_path_semantics_match_across_backends(
    tmp_path: Path,
) -> None:
    snapshot = Snapshot("generic", "memory:test", "generic", datetime.now(UTC))
    parsed = [
        entry(("Users", "Foo")),
        entry(("Users", "foo"), line=2),
        entry(("Volumes", "Caf\u00e9"), line=3),
    ]
    memory_builder = InMemorySnapshotBuilder(snapshot)
    sqlite_builder = SQLiteSnapshotBuilder(snapshot, tmp_path / "generic.db")
    for item in parsed:
        memory_builder.add(item)
        sqlite_builder.add(item)
    memory = memory_builder.finish()
    with sqlite_builder.finish() as sqlite_store:
        assert list(sqlite_store.iter_nodes()) == list(memory.iter_nodes())
    with open_sqlite_store(tmp_path / "generic.db") as reopened:
        users = reopened.lookup(1, b"Users")
        assert users is not None
        assert [node.mounted_name for node in reopened.iter_children(users.id)] == [
            b"Foo",
            b"foo",
        ]


@pytest.mark.parametrize("builder_kind", ["memory", "sqlite"])
def test_non_unicode_component_is_rejected_by_both_backends(
    tmp_path: Path, builder_kind: str
) -> None:
    snapshot = Snapshot("path", "memory:test", "generic", datetime.now(UTC))
    build = (
        InMemorySnapshotBuilder(snapshot)
        if builder_kind == "memory"
        else SQLiteSnapshotBuilder(snapshot, tmp_path / "path.db")
    )
    item = entry(("bad\ud800name",))
    with pytest.raises(BuildError, match="component is not valid Unicode"):
        build.add(item)
    build.abort()


def test_duplicates_conflicts_and_non_json_metadata(tmp_path: Path) -> None:
    destination = tmp_path / "snapshot.db"
    parser = EntriesParser([entry(r"C:\Same"), entry(r"C:\Same", line=2)])
    with create_sqlite_store(MemorySource(), parser, destination) as store:
        drive = store.lookup(1, b"C")
        assert drive is not None
        assert [node.mounted_name for node in store.iter_children(drive.id)] == [
            b"Same"
        ]

    conflict = EntriesParser(
        [
            entry(r"C:\same"),
            entry(r"C:\same", NodeKind.FILE, Observation.FILE_ENTRY, 0, 2),
        ]
    )
    with pytest.raises(ImportFailure):
        create_sqlite_store(MemorySource(), conflict, tmp_path / "conflict.db")
    assert not (tmp_path / "conflict.db").exists()

    with pytest.raises(TypeError, match="unsupported metadata value set"):
        entry(r"C:\bad", metadata={"value": {1, 2}})


def test_existing_destination_overwrite_and_failure_atomicity(tmp_path: Path) -> None:
    destination = tmp_path / "snapshot.db"
    first = create_sqlite_store(
        MemorySource(), EntriesParser([entry(r"C:\old")]), destination
    )
    old_id = next(iter(first.iter_nodes())).snapshot_id
    first.close()

    with pytest.raises(SQLiteDestinationExistsError):
        create_sqlite_store(
            MemorySource(), EntriesParser([entry(r"C:\new")]), destination
        )
    with open_sqlite_store(destination) as unchanged:
        assert unchanged.get_snapshot(old_id).id == old_id

    conflict = EntriesParser(
        [
            entry(r"C:\same"),
            entry(r"C:\same", NodeKind.FILE, Observation.FILE_ENTRY, 0, line=2),
        ]
    )
    with pytest.raises(ImportFailure):
        create_sqlite_store(MemorySource(), conflict, destination, overwrite=True)
    with open_sqlite_store(destination) as unchanged:
        assert unchanged.get_snapshot(old_id).id == old_id

    with pytest.raises(RuntimeError, match="parser failed"):
        create_sqlite_store(
            MemorySource(),
            EntriesParser([entry(r"C:\new")], fail=True),
            destination,
            overwrite=True,
        )
    with open_sqlite_store(destination) as unchanged:
        assert unchanged.get_snapshot(old_id).id == old_id
    assert not list(tmp_path.glob(".snapshot.db.*"))

    replaced = create_sqlite_store(
        MemorySource(), EntriesParser([entry(r"C:\new")]), destination, overwrite=True
    )
    assert next(iter(replaced.iter_nodes())).snapshot_id != old_id
    replaced.close()


def test_missing_corrupt_schema_mismatch_and_close(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    with pytest.raises(SQLiteStoreError, match=str(missing)):
        open_sqlite_store(missing)
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not sqlite")
    with pytest.raises(SQLiteSchemaError, match=str(corrupt)):
        open_sqlite_store(corrupt)

    path = tmp_path / "version.db"
    store = create_sqlite_store(MemorySource(), EntriesParser([]), path)
    store.close()
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 999")
    with pytest.raises(SQLiteSchemaError, match=r"unsupported schema version 999"):
        open_sqlite_store(path)

    valid = tmp_path / "close.db"
    store = create_sqlite_store(MemorySource(), EntriesParser([]), valid)
    store.close()
    store.close()
    with pytest.raises(SQLiteStoreClosedError, match="closed"):
        list(store.iter_nodes())


def test_nullable_content_reference_and_status_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "remote.db"
    store = create_sqlite_store(
        MemorySource(),
        EntriesParser([entry(r"C:\remote", NodeKind.FILE, Observation.FILE_ENTRY, 4)]),
        path,
    )
    remote = next(node for node in store.iter_nodes() if node.mounted_name == b"remote")
    store.close()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE nodes SET content_status = 'remote', content_ref = ? WHERE id = ?",
            ("https://example.invalid/content", remote.id),
        )
    with open_sqlite_store(path) as reopened:
        node = reopened.get_node(remote.id)
        assert node.content is None
        assert node.content_status.value == "remote"
        assert node.content_ref == "https://example.invalid/content"


def test_cli_create_show_and_mount_close(
    listing_file: Path, tmp_path: Path, capsys, monkeypatch
) -> None:
    artifact = tmp_path / "listing.snapshot"
    selectors = ["--source", "file", "--parser", "windows-dir"]
    assert (
        main(["sqlite", "create", str(artifact), str(listing_file), *selectors])
        == 0
    )
    assert main(["sqlite", "show", str(artifact), "--json"]) == 0
    assert '"source_format": "windows-dir"' in capsys.readouterr().out

    captured = None

    def fake_mount(store, mountpoint: str, *, simulate_missing_content: bool) -> None:
        nonlocal captured
        captured = store
        assert mountpoint == str(tmp_path / "mount")
        assert simulate_missing_content
        assert list(store.iter_nodes())

    monkeypatch.setattr(api, "mount_store", fake_mount)
    assert (
        main(
            [
                "sqlite",
                "mount",
                str(artifact),
                str(tmp_path / "mount"),
                "--simulate-missing-content",
            ]
        )
        == 0
    )
    assert captured is not None
    with pytest.raises(SQLiteStoreClosedError):
        list(captured.iter_nodes())


def test_cli_create_can_mount_immediately_and_closes(
    listing_file: Path, tmp_path: Path, monkeypatch
) -> None:
    artifact = tmp_path / "mounted.snapshot"
    mountpoint = tmp_path / "mount"
    captured = None

    def fake_mount(store, path: str, *, simulate_missing_content: bool) -> None:
        nonlocal captured
        captured = store
        assert path == str(mountpoint)
        assert simulate_missing_content
        assert list(store.iter_nodes())

    monkeypatch.setattr(api, "mount_store", fake_mount)
    assert (
        main(
            [
                "sqlite",
                "create",
                str(artifact),
                str(listing_file),
                "--source",
                "file",
                "--parser",
                "windows-dir",
                "--mount",
                str(mountpoint),
                "--simulate-missing-content",
            ]
        )
        == 0
    )
    assert captured is not None
    with pytest.raises(SQLiteStoreClosedError):
        list(captured.iter_nodes())
