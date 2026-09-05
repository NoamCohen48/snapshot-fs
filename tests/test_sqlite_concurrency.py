from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest

from snapshotfs.model import NodeKind, Observation, ParsedEntry, Snapshot
from snapshotfs.stores.memory import InMemorySnapshotBuilder
from snapshotfs.stores.sqlite import (
    SQLiteSnapshotBuilder,
    SQLiteStoreClosedError,
)


def stores(path: Path):
    snapshot = Snapshot("test", "memory:test", "test", datetime.now(UTC))
    memory_builder = InMemorySnapshotBuilder(snapshot)
    sqlite_builder = SQLiteSnapshotBuilder(snapshot, path)
    for name in ("a", "b", "c"):
        item = ParsedEntry(
            (name,),
            NodeKind.DIRECTORY,
            Observation.SECTION_HEADER,
            None,
            None,
            1,
        )
        memory_builder.add(item)
        sqlite_builder.add(item)
    return memory_builder.finish(), sqlite_builder.finish()


@pytest.mark.parametrize("offset", [10**100, -(10**100)])
def test_arbitrarily_large_offsets_match_memory(tmp_path: Path, offset: int) -> None:
    memory, sqlite_store = stores(tmp_path / "snapshot.db")
    try:
        assert [
            node.mounted_name for node in memory.iter_children(1, offset)
        ] == [
            node.mounted_name
            for node in sqlite_store.iter_children(1, offset)
        ]
    finally:
        sqlite_store.close()


def test_concurrent_reads_and_close_only_return_closed_error(tmp_path: Path) -> None:
    _, store = stores(tmp_path / "snapshot.db")
    barrier = Barrier(9)

    def read_until_closed() -> type[Exception] | None:
        barrier.wait()
        for _ in range(200):
            try:
                tuple(store.iter_nodes())
                store.lookup(1, b"a")
                _ = store.diagnostics
            except Exception as exc:
                return type(exc)
        return None

    def close() -> None:
        barrier.wait()
        store.close()

    with ThreadPoolExecutor(max_workers=9) as executor:
        readers = [executor.submit(read_until_closed) for _ in range(8)]
        closer = executor.submit(close)
        closer.result()
        outcomes = [future.result() for future in readers]
    assert all(item in {None, SQLiteStoreClosedError} for item in outcomes)
    with pytest.raises(SQLiteStoreClosedError):
        tuple(store.iter_nodes())
