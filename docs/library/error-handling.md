# Error Handling

[Python library](index.md)

```python
from snapshotfs import (
    FileSource,
    ImportFailure,
    SQLiteDestinationExistsError,
    SQLitePersistenceError,
    SourceError,
    WindowsDirParser,
    create_sqlite_store,
)

try:
    store = create_sqlite_store(
        FileSource("listing.txt"),
        WindowsDirParser(),
        "backup.snapshot",
    )
except SourceError as exc:
    print(f"source unavailable: {exc}")
except ImportFailure as exc:
    for diagnostic in exc.diagnostics:
        print(diagnostic.severity, diagnostic.code, diagnostic.message)
    print(f"{exc.diagnostic_count} diagnostic(s) in total")
except SQLiteDestinationExistsError as exc:
    print(f"destination exists: {exc.path}")
except SQLitePersistenceError as exc:
    print(f"persistence failure at {exc.path}: {exc.detail}")
else:
    store.close()
```

## Error Categories

`SourceError`
: An `OSError` raised when a source cannot inspect or open its input.

`ImportFailure`
: A validation failure containing retained structured `diagnostics` and the
  complete `diagnostic_count`.

`SQLiteStoreError`
: Base class for SQLite persistence, schema, and closed-store errors. Instances
  expose `path` and `detail`.

`FuseUnavailableError`
: The optional Python FUSE dependencies are missing. Host mount errors such as
  permissions or an unusable mountpoint are not wrapped in this type.

`SQLiteDurabilityError` and `SQLitePublicationError` indicate failures after
publication may already have occurred. Catch them separately when the caller
must determine whether the destination changed.
