"""SQLite-backed snapshot artifacts."""

from pathlib import Path

from snapshotfs.import_service import _create_store
from snapshotfs.parser import Parser
from snapshotfs.source import Source
from snapshotfs.store.sqlite.builder import SQLiteSnapshotBuilder
from snapshotfs.store.sqlite.errors import (
    SQLiteDestinationExistsError,
    SQLiteDurabilityError,
    SQLitePersistenceError,
    SQLitePublicationError,
    SQLiteSchemaError,
    SQLiteStoreClosedError,
    SQLiteStoreError,
)
from snapshotfs.store.sqlite.store import SQLiteSnapshotStore, open_sqlite_store


def create_sqlite_store(
    source: Source,
    parser: Parser,
    destination: str | Path,
    *,
    overwrite: bool = False,
) -> SQLiteSnapshotStore:
    """Import a source and atomically publish a SQLite-backed store."""
    return _create_store(
        source,
        parser,
        lambda snapshot: SQLiteSnapshotBuilder(
            snapshot, destination, overwrite=overwrite
        ),
    )


__all__ = [
    "SQLiteDestinationExistsError",
    "SQLiteDurabilityError",
    "SQLitePersistenceError",
    "SQLitePublicationError",
    "SQLiteSchemaError",
    "SQLiteSnapshotBuilder",
    "SQLiteSnapshotStore",
    "SQLiteStoreClosedError",
    "SQLiteStoreError",
    "create_sqlite_store",
    "open_sqlite_store",
]
