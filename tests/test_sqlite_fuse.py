import importlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from snapshotfs.model import NodeKind, Observation, ParsedEntry, Snapshot
from snapshotfs.stores.sqlite import SQLiteSnapshotBuilder

pyfuse3 = pytest.importorskip("pyfuse3")
trio = pytest.importorskip("trio")
SnapshotOperations = importlib.import_module(
    "snapshotfs.fuse.adapter"
).SnapshotOperations


def test_fuse_adapter_reads_sqlite_store(tmp_path: Path) -> None:
    builder = SQLiteSnapshotBuilder(
        Snapshot("test", "memory:test", "test", datetime.now(UTC)),
        tmp_path / "snapshot.db",
    )
    builder.add(
        ParsedEntry(
            ("inline",),
            NodeKind.FILE,
            Observation.FILE_ENTRY,
            3,
            datetime(2024, 1, 1),
            1,
            b"abc",
        )
    )
    with builder.finish() as store:
        operations = SnapshotOperations(store)

        async def exercise() -> None:
            inline = await operations.lookup(1, b"inline", None)
            handle = await operations.open(inline.st_ino, 0, None)
            assert await operations.read(handle.fh, 1, 2) == b"bc"
            await operations.release(handle.fh)

        trio.run(exercise)
