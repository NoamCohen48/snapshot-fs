from snapshotfs.fuse import FuseUnavailableError, mount_store
from snapshotfs.parser import DateFormat, Parser, ParseResult, WindowsDirParser
from snapshotfs.parser.base import Parser as BaseParser
from snapshotfs.parser.base import ParseResult as BaseParseResult
from snapshotfs.parser.windows_dir import DateFormat as ParserDateFormat
from snapshotfs.parser.windows_dir import WindowsDirParser as ConcreteWindowsDirParser
from snapshotfs.source import FileSource, Source, SourceError
from snapshotfs.source.base import Source as BaseSource
from snapshotfs.source.file import FileSource as ConcreteFileSource
from snapshotfs.source.file import SourceError as ConcreteSourceError
from snapshotfs.store import ImportFailure, SnapshotStore
from snapshotfs.store.base import ImportFailure as BaseImportFailure
from snapshotfs.store.base import SnapshotStore as BaseSnapshotStore
from snapshotfs.store.memory import (
    BuildError,
    InMemorySnapshotBuilder,
    InMemorySnapshotStore,
    create_memory_store,
)
from snapshotfs.store.memory.builder import (
    InMemorySnapshotBuilder as MemoryBuilder,
)
from snapshotfs.store.memory.errors import BuildError as MemoryBuildError
from snapshotfs.store.memory.store import InMemorySnapshotStore as MemoryStore
from snapshotfs.store.sqlite import create_sqlite_store


def test_source_module_exports_public_types() -> None:
    assert Source is BaseSource
    assert FileSource is ConcreteFileSource
    assert SourceError is ConcreteSourceError


def test_parser_module_exports_public_types() -> None:
    assert Parser is BaseParser
    assert ParseResult is BaseParseResult
    assert DateFormat is ParserDateFormat
    assert WindowsDirParser is ConcreteWindowsDirParser


def test_store_modules_export_public_types_and_factories() -> None:
    assert ImportFailure is BaseImportFailure
    assert SnapshotStore is BaseSnapshotStore
    assert BuildError is MemoryBuildError
    assert InMemorySnapshotBuilder is MemoryBuilder
    assert InMemorySnapshotStore is MemoryStore
    assert callable(create_memory_store)
    assert callable(create_sqlite_store)


def test_fuse_module_exports_mount_api() -> None:
    assert issubclass(FuseUnavailableError, RuntimeError)
    assert callable(mount_store)
