from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import BinaryIO

import pytest

from snapshotfs.diagnostics import DiagnosticCollector
from snapshotfs.import_service import (
    ImportFailure,
    create_memory_store,
    create_sqlite_store,
)
from snapshotfs.model import (
    ContentStatus,
    NodeKind,
    Observation,
    ParsedEntry,
    Snapshot,
)
from snapshotfs.parsers.base import ParseResult
from snapshotfs.parsers.windows_dir import WindowsDirParser
from snapshotfs.parsers.windows_dir.paths import to_mounted_path
from snapshotfs.sources.file import FileSource
from snapshotfs.stores.memory import BuildError, InMemorySnapshotBuilder


def import_text(tmp_path: Path, text: str):
    path = tmp_path / "listing.txt"
    path.write_bytes(text.encode())
    return create_memory_store(FileSource(path), WindowsDirParser())


def builder() -> InMemorySnapshotBuilder:
    return InMemorySnapshotBuilder(
        Snapshot("test", "file:///test", "windows-dir", datetime.now(UTC))
    )


def entry(
    path: str | tuple[str, ...],
    kind: NodeKind = NodeKind.DIRECTORY,
    observation: Observation = Observation.SECTION_HEADER,
    size: int | None = None,
    modified: datetime | None = None,
    line: int = 1,
) -> ParsedEntry:
    mounted_path = (
        to_mounted_path(PureWindowsPath(path)) if isinstance(path, str) else path
    )
    return ParsedEntry(mounted_path, kind, observation, size, modified, line)


def test_normalizes_drive_synthesizes_parents_and_sorts_bytes(
    tmp_path: Path, listing_text: str
) -> None:
    store = import_text(tmp_path, listing_text)
    root = store.get_root(next(iter(store.iter_nodes())).snapshot_id)
    drive = store.lookup(root.id, b"C")
    assert drive is not None
    users = store.lookup(drive.id, b"Users")
    assert users is not None
    alice = store.lookup(users.id, b"Alice")
    assert alice is not None
    children = list(store.iter_children(alice.id))
    assert [node.mounted_name for node in children] == [b"Documents", b"notes file.txt"]
    assert store.lookup(alice.id, b"documents") is None
    assert children[0].modified_at == datetime(2024, 1, 2, 15, 4)
    assert children[0].source_line == 6


def test_zero_byte_content_is_present_and_nonempty_is_missing() -> None:
    build = builder()
    timestamp = datetime(2024, 1, 1)
    build.add(entry(r"C:\zero", NodeKind.FILE, Observation.FILE_ENTRY, 0, timestamp))
    build.add(entry(r"C:\full", NodeKind.FILE, Observation.FILE_ENTRY, 1, timestamp, 2))
    store = build.finish()
    drive = store.lookup(1, b"C")
    assert drive is not None
    assert store.lookup(drive.id, b"zero").content_status is ContentStatus.PRESENT  # type: ignore[union-attr]
    assert store.lookup(drive.id, b"full").content_status is ContentStatus.MISSING  # type: ignore[union-attr]
    assert store.lookup(drive.id, b"zero").content == b""  # type: ignore[union-attr]
    assert store.lookup(drive.id, b"full").content is None  # type: ignore[union-attr]


def test_directory_content_is_not_applicable() -> None:
    build = builder()
    build.add(entry(r"C:\directory"))
    store = build.finish()
    drive = store.lookup(1, b"C")
    assert drive is not None
    directory = store.lookup(drive.id, b"directory")
    assert directory is not None
    assert directory.content is None
    assert directory.content_status is ContentStatus.NOT_APPLICABLE


def test_paths_are_exact_and_case_sensitive() -> None:
    build = builder()
    build.add(entry(r"c:\Foo"))
    build.add(entry(r"C:\foo", line=2))
    store = build.finish()

    drive = store.lookup(1, b"C")
    assert drive is not None
    assert [node.mounted_name for node in store.iter_children(drive.id)] == [
        b"Foo",
        b"foo",
    ]


def test_synthesized_parent_is_enriched_by_later_explicit_entry() -> None:
    build = builder()
    build.add(entry(r"C:\parent\child"))
    modified = datetime(2024, 2, 3, 4, 5)
    build.add(
        entry(
            r"C:\parent",
            NodeKind.DIRECTORY,
            Observation.DIRECTORY_ENTRY,
            modified=modified,
            line=2,
        )
    )
    store = build.finish()
    drive = store.lookup(1, b"C")
    assert drive is not None
    parent = store.lookup(drive.id, b"parent")
    assert parent is not None
    assert parent.modified_at == modified
    assert parent.source_line == 2
    assert parent.original_path == "C/parent"


def test_synthesized_parents_store_their_own_relative_path_prefix() -> None:
    build = builder()
    build.add(entry(("a", "b", "c")))
    store = build.finish()
    first = store.lookup(1, b"a")
    assert first is not None and first.original_path == "a"
    second = store.lookup(first.id, b"b")
    assert second is not None and second.original_path == "a/b"
    third = store.lookup(second.id, b"c")
    assert third is not None and third.original_path == "a/b/c"


def test_non_ascii_names_are_exact() -> None:
    build = builder()
    build.add(entry("C:\\\N{LATIN SMALL LETTER E WITH ACUTE}"))
    build.add(entry("C:\\\N{LATIN CAPITAL LETTER E WITH ACUTE}", line=2))
    store = build.finish()
    drive = store.lookup(1, b"C")
    assert drive is not None
    assert len(list(store.iter_children(drive.id))) == 2


@pytest.mark.parametrize(
    "incoming",
    [
        entry(
            r"C:\same",
            NodeKind.FILE,
            Observation.FILE_ENTRY,
            1,
            datetime(2024, 1, 1),
            2,
        ),
        entry(
            r"C:\same",
            NodeKind.DIRECTORY,
            Observation.DIRECTORY_ENTRY,
            None,
            datetime(2024, 1, 2),
            2,
        ),
    ],
)
def test_type_and_metadata_conflicts_identify_both_lines(incoming: ParsedEntry) -> None:
    build = builder()
    build.add(
        entry(
            r"C:\same",
            NodeKind.FILE,
            Observation.FILE_ENTRY,
            0,
            datetime(2024, 1, 1),
        )
    )

    with pytest.raises(BuildError, match=r"line 1.*line 2"):
        build.add(incoming)


def test_duplicate_directory_metadata_conflicts() -> None:
    build = builder()
    build.add(
        entry(
            r"C:\same",
            NodeKind.DIRECTORY,
            Observation.DIRECTORY_ENTRY,
            modified=datetime(2024, 1, 1),
        )
    )
    with pytest.raises(BuildError, match=r"line 1.*line 2"):
        build.add(
            entry(
                r"C:\same",
                NodeKind.DIRECTORY,
                Observation.DIRECTORY_ENTRY,
                modified=datetime(2024, 1, 2),
                line=2,
            )
        )


def test_conflicts_without_line_numbers_use_original_path_provenance() -> None:
    build = builder()
    first = ParsedEntry(
        ("same",),
        NodeKind.FILE,
        Observation.FILE_ENTRY,
        1,
        None,
    )
    second = ParsedEntry(
        ("same",),
        NodeKind.FILE,
        Observation.FILE_ENTRY,
        2,
        None,
    )
    build.add(first)
    with pytest.raises(BuildError, match=r"path 'same'"):
        build.add(second)


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("safe", ".."),
        ("bad\x00name",),
        ("bad/name",),
        ("safe", ""),
    ],
)
def test_rejects_unsafe_mounted_components(path: tuple[str, ...]) -> None:
    build = builder()
    with pytest.raises(BuildError):
        build.add(entry(path))


def test_generic_paths_preserve_parser_defined_hierarchy_and_case() -> None:
    build = builder()
    build.add(entry(("Users", "Foo")))
    build.add(entry(("Users", "foo"), line=2))
    build.add(entry((r"lib\name:part",), line=3))
    store = build.finish()

    users = store.lookup(1, b"Users")
    assert users is not None
    assert [node.mounted_name for node in store.iter_children(users.id)] == [
        b"Foo",
        b"foo",
    ]
    archive_name = store.lookup(1, br"lib\name:part")
    assert archive_name is not None
    assert archive_name.original_path == r"lib\name:part"


def test_failed_parse_never_returns_a_store(tmp_path: Path) -> None:
    path = tmp_path / "bad.txt"
    path.write_bytes(b"unknown\n")
    with pytest.raises(ImportFailure) as caught:
        create_memory_store(FileSource(path), WindowsDirParser())
    assert caught.value.diagnostics[0].line_number == 1


def test_import_consumes_entries_while_source_stream_is_open(tmp_path: Path) -> None:
    path = tmp_path / "lazy.bin"
    path.write_bytes(b"unused")

    class LazyParser:
        format_name = "lazy"
        consumed_with_open = False

        def parse(self, stream: BinaryIO) -> ParseResult:
            diagnostics = DiagnosticCollector()

            def entries():
                assert not stream.closed
                self.consumed_with_open = True
                diagnostics.warning("TEST_WARNING", "retained warning", 1)
                yield entry(r"C:\lazy")

            return ParseResult(entries(), diagnostics)

    parser = LazyParser()
    store = create_memory_store(FileSource(path), parser)

    assert parser.consumed_with_open
    assert store.diagnostics[0].code == "TEST_WARNING"
    assert store.diagnostic_count == 1


def test_unretained_parser_error_still_prevents_publication(tmp_path: Path) -> None:
    path = tmp_path / "diagnostics.bin"
    path.write_bytes(b"unused")

    class DiagnosticParser:
        format_name = "diagnostics"

        def parse(self, stream: BinaryIO) -> ParseResult:
            diagnostics = DiagnosticCollector()

            def entries():
                for number in range(1000):
                    diagnostics.warning("WARNING", "warning", number + 1)
                diagnostics.error("LATE_ERROR", "not retained", 1001)
                if False:
                    yield entry(r"C:\unreachable")

            return ParseResult(entries(), diagnostics)

    with pytest.raises(ImportFailure) as caught:
        create_memory_store(FileSource(path), DiagnosticParser())
    assert caught.value.diagnostic_count == 1001
    assert len(caught.value.diagnostics) == 1000


def test_full_diagnostics_retain_builder_conflict_details(tmp_path: Path) -> None:
    path = tmp_path / "conflict.bin"
    path.write_bytes(b"unused")

    class ConflictParser:
        format_name = "conflict"

        def parse(self, stream: BinaryIO) -> ParseResult:
            diagnostics = DiagnosticCollector()

            def entries():
                for number in range(1000):
                    diagnostics.warning("WARNING", "warning", number + 1)
                yield entry(
                    r"C:\same",
                    NodeKind.FILE,
                    Observation.FILE_ENTRY,
                    1,
                    datetime(2024, 1, 1),
                    1,
                )
                yield entry(
                    r"C:\same",
                    NodeKind.FILE,
                    Observation.FILE_ENTRY,
                    2,
                    datetime(2024, 1, 1),
                    1002,
                )

            return ParseResult(entries(), diagnostics)

    with pytest.raises(ImportFailure) as caught:
        create_memory_store(FileSource(path), ConflictParser())

    conflicts = [
        item for item in caught.value.diagnostics if item.code == "ENTRY_CONFLICT"
    ]
    assert len(caught.value.diagnostics) == 1000
    assert caught.value.diagnostic_count == 1001
    assert len(conflicts) == 1
    assert conflicts[0].line_number == 1002
    assert "line 1" in conflicts[0].message
    assert "line 1002" in conflicts[0].message


def test_finished_store_and_nodes_are_immutable() -> None:
    build = builder()
    build.add(entry(r"C:\dir"))
    store = build.finish()
    with pytest.raises(RuntimeError):
        build.add(entry(r"C:\other"))
    with pytest.raises((AttributeError, TypeError)):
        store.get_node(1).mounted_name = b"changed"  # type: ignore[misc]


def test_multibyte_overlong_mounted_name_fails_both_import_backends(
    tmp_path: Path,
) -> None:
    name = "\u00e9" * 128
    text = f""" Directory of C:\\\n
01/02/2024 10:00 0 {name}
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    source_path = tmp_path / "overlong.txt"
    source_path.write_text(text)
    source = FileSource(source_path)
    with pytest.raises(ImportFailure) as memory_failure:
        create_memory_store(source, WindowsDirParser())
    destination = tmp_path / "overlong.db"
    with pytest.raises(ImportFailure) as sqlite_failure:
        create_sqlite_store(source, WindowsDirParser(), destination)
    for failure in (memory_failure.value, sqlite_failure.value):
        diagnostic = next(
            item for item in failure.diagnostics if item.code == "INVALID_PATH"
        )
        assert diagnostic.line_number == 3
        assert "255-byte" in diagnostic.message
    assert not destination.exists()
