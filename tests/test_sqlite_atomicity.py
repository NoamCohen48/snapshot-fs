import io
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Event
from typing import BinaryIO

import pytest

import snapshotfs.stores.sqlite.artifact as artifact
from snapshotfs.import_service import create_sqlite_store
from snapshotfs.model import NodeKind, Observation, ParsedEntry, Snapshot
from snapshotfs.parsers.base import ParseResult
from snapshotfs.stores.sqlite import (
    SQLiteDestinationExistsError,
    SQLiteDurabilityError,
    SQLitePublicationError,
    SQLiteSnapshotBuilder,
    open_sqlite_store,
)


def builder(path: Path, name: str, *, overwrite: bool) -> SQLiteSnapshotBuilder:
    result = SQLiteSnapshotBuilder(
        Snapshot(name, "memory:test", "test", datetime.now(UTC)),
        path,
        overwrite=overwrite,
    )
    result.add(
        ParsedEntry(
            (name,),
            NodeKind.DIRECTORY,
            Observation.SECTION_HEADER,
            None,
            None,
            1,
        )
    )
    return result


def test_no_overwrite_is_race_safe_and_overwrite_is_last_finisher_wins(
    tmp_path: Path,
) -> None:
    path = tmp_path / "race.db"
    barrier = Barrier(2)

    def compete(name: str) -> str | type[Exception]:
        candidate = builder(path, name, overwrite=False)
        barrier.wait()
        try:
            candidate.finish().close()
        except SQLiteDestinationExistsError:
            return SQLiteDestinationExistsError
        return name

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(compete, name) for name in ("first", "second")]
        outcomes = [future.result() for future in futures]
    winner = next(item for item in outcomes if isinstance(item, str))
    assert outcomes.count(SQLiteDestinationExistsError) == 1
    with open_sqlite_store(path) as store:
        assert store.get_snapshot(winner).id == winner

    overwrite_barrier = Barrier(2)
    earlier_published = Event()

    def overwrite(name: str, wait_for_earlier: bool) -> None:
        candidate = builder(path, name, overwrite=True)
        overwrite_barrier.wait()
        if wait_for_earlier:
            earlier_published.wait()
        candidate.finish().close()
        if not wait_for_earlier:
            earlier_published.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(overwrite, "earlier", False),
            executor.submit(overwrite, "later", True),
        ]
        for future in futures:
            future.result()
    with open_sqlite_store(path) as store:
        assert store.get_snapshot("later").id == "later"


def test_directory_fsync_failure_reports_published_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    temporary = tmp_path / "temporary"
    destination = tmp_path / "snapshot.db"
    temporary.write_bytes(b"artifact")
    real_fsync = os.fsync
    calls = 0
    monkeypatch.setattr(artifact, "DIRECTORY_FSYNC_SUPPORTED", True)

    def fail_directory_fsync(file_descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("directory sync failed")
        real_fsync(file_descriptor)

    monkeypatch.setattr(artifact.os, "fsync", fail_directory_fsync)
    with pytest.raises(SQLiteDurabilityError, match="was published"):
        artifact.publish(temporary, destination, overwrite=False)
    assert destination.read_bytes() == b"artifact"


def test_publication_skips_unsupported_directory_fsync(
    tmp_path: Path, monkeypatch
) -> None:
    temporary = tmp_path / "temporary"
    destination = tmp_path / "snapshot.db"
    temporary.write_bytes(b"artifact")
    monkeypatch.setattr(artifact, "DIRECTORY_FSYNC_SUPPORTED", False)

    def unexpected_open(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("directory open must be skipped")

    monkeypatch.setattr(artifact.os, "open", unexpected_open)
    artifact.publish(temporary, destination, overwrite=False)
    assert destination.read_bytes() == b"artifact"


def test_no_overwrite_temp_unlink_failure_never_deletes_destination(
    tmp_path: Path, monkeypatch
) -> None:
    temporary = tmp_path / "temporary"
    destination = tmp_path / "snapshot.db"
    other_writer = tmp_path / "other"
    temporary.write_bytes(b"artifact")
    other_writer.write_bytes(b"other-writer")
    real_unlink = Path.unlink

    def fail_temporary_unlink(path: Path, *args, **kwargs) -> None:
        if path == temporary:
            os.replace(other_writer, destination)
            raise OSError("cannot unlink temporary")
        real_unlink(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, "unlink", fail_temporary_unlink)
        with pytest.raises(SQLitePublicationError, match="was published"):
            artifact.publish(temporary, destination, overwrite=False)
    assert destination.read_bytes() == b"other-writer"
    temporary.unlink()


class Source:
    uri = "memory:test"
    size = 0

    def open(self) -> AbstractContextManager[BinaryIO]:
        return nullcontext(io.BytesIO())


class FailingParser:
    format_name = "failing"

    def parse(self, stream: BinaryIO) -> ParseResult:
        del stream

        def entries():
            if False:
                yield
            raise RuntimeError("original parser failure")

        from snapshotfs.diagnostics import DiagnosticCollector

        return ParseResult(entries(), DiagnosticCollector())


def test_cleanup_error_never_masks_original_import_failure(
    tmp_path: Path, monkeypatch
) -> None:
    destination = tmp_path / "snapshot.db"
    real_unlink = Path.unlink

    with monkeypatch.context() as context:
        context.setattr(
            Path,
            "unlink",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("cleanup failed")),
        )
        with pytest.raises(RuntimeError, match="original parser failure"):
            create_sqlite_store(Source(), FailingParser(), destination)
    assert not destination.exists()
    for temporary in tmp_path.glob(".snapshot.db.*"):
        real_unlink(temporary)
