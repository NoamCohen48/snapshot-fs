"""Atomic builder and immutable in-memory snapshot store."""

from snapshotfs.import_service import _create_store
from snapshotfs.parser import Parser
from snapshotfs.source import Source
from snapshotfs.store.memory.builder import InMemorySnapshotBuilder
from snapshotfs.store.memory.errors import BuildError
from snapshotfs.store.memory.store import InMemorySnapshotStore


def create_memory_store(
    source: Source, parser: Parser
) -> InMemorySnapshotStore:
    """Import a source into an immutable in-memory store."""
    return _create_store(source, parser, InMemorySnapshotBuilder)


__all__ = [
    "BuildError",
    "InMemorySnapshotBuilder",
    "InMemorySnapshotStore",
    "create_memory_store",
]
