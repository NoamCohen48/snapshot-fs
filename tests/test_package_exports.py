from snapshotfs.parsers import Parser, ParseResult
from snapshotfs.parsers.base import Parser as BaseParser
from snapshotfs.parsers.base import ParseResult as BaseParseResult
from snapshotfs.sources import FileSource, Source, SourceError
from snapshotfs.sources.base import Source as BaseSource
from snapshotfs.sources.file import FileSource as ConcreteFileSource
from snapshotfs.sources.file import SourceError as ConcreteSourceError
from snapshotfs.stores import (
    BuildError,
    InMemorySnapshotBuilder,
    InMemorySnapshotStore,
    SnapshotStore,
)
from snapshotfs.stores.base import SnapshotStore as BaseSnapshotStore
from snapshotfs.stores.memory import BuildError as MemoryBuildError
from snapshotfs.stores.memory import InMemorySnapshotBuilder as MemoryBuilder
from snapshotfs.stores.memory import InMemorySnapshotStore as MemoryStore


def test_sources_package_exports_public_types() -> None:
    assert Source is BaseSource
    assert FileSource is ConcreteFileSource
    assert SourceError is ConcreteSourceError


def test_parsers_package_exports_public_types() -> None:
    assert Parser is BaseParser
    assert ParseResult is BaseParseResult


def test_stores_package_exports_public_types() -> None:
    assert SnapshotStore is BaseSnapshotStore
    assert BuildError is MemoryBuildError
    assert InMemorySnapshotBuilder is MemoryBuilder
    assert InMemorySnapshotStore is MemoryStore
