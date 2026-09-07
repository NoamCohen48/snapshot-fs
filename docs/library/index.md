# Python Library

[Documentation](../index.md)

SnapshotFS exposes an explicit composition pipeline:

```text
Source -> Parser -> import service -> SnapshotStore -> optional FUSE mount
```

Create a source and parser, then choose an in-memory or SQLite-backed store:

```python
from snapshotfs import FileSource, WindowsDirParser, create_memory_store

source = FileSource("listing.txt")
parser = WindowsDirParser(encoding="cp1252", date_format="mdy")
store = create_memory_store(source, parser)

for node in store.iter_nodes():
    print(node.id, node.mounted_name, node.kind)
```

Import from `snapshotfs` for the primary public API. Specialized contracts are
available from `snapshotfs.model`, `snapshotfs.parsers`, `snapshotfs.sources`,
and `snapshotfs.stores`.

## Guides

- [Importing listings](importing.md)
- [Reading memory and SQLite stores](stores.md)
- [Sources and parsers](parsers-and-sources.md)
- [Mounting a store](mounting.md)
- [Handling errors](error-handling.md)
- [Python API reference](../reference/api.md)

Imports are all-or-nothing, snapshots are immutable, and mounting is optional.
A listing normally provides metadata rather than file bytes.
