# Importing Listings

[Python library](index.md)

## Memory Store

```python
from snapshotfs import FileSource, WindowsDirParser, create_memory_store

store = create_memory_store(
    FileSource("listing.txt"),
    WindowsDirParser(encoding="utf-8", date_format="mdy"),
)
```

The returned `InMemorySnapshotStore` needs no explicit cleanup.

## SQLite Store

```python
from snapshotfs import FileSource, WindowsDirParser, create_sqlite_store

with create_sqlite_store(
    FileSource("listing.txt"),
    WindowsDirParser(),
    "backup.snapshot",
) as store:
    print(tuple(store.iter_nodes()))
```

An existing destination raises `SQLiteDestinationExistsError`. Pass
`overwrite=True` to replace it atomically after a successful import.

## Import Behavior

SnapshotFS keeps the source stream open while consuming the parser's single-pass
entry iterator. It incrementally validates and adds entries to an unpublished
builder. Parser errors, unsafe paths, incompatible duplicates, and tree
conflicts raise `ImportFailure` and abort the builder.

Warnings do not prevent publication. Successful stores expose retained warnings
through `store.diagnostics` and the complete count through
`store.diagnostic_count`.

Missing ancestors are synthesized. Exact duplicate observations can merge, but
file/directory conflicts and incompatible metadata fail the import. Paths and
lookups remain case-sensitive.
