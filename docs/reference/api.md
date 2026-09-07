# Python API Reference

[Documentation](../index.md)

The primary API is exported from `snapshotfs`. The generated reference below
uses that tested export surface rather than documenting implementation modules.

## Composition

```python
create_memory_store(source, parser)
create_sqlite_store(source, parser, destination, *, overwrite=False)
open_sqlite_store(path)
mount_store(store, mountpoint, *, simulate_missing_content=False)
```

`create_memory_store()` returns an `InMemorySnapshotStore`.
`create_sqlite_store()` and `open_sqlite_store()` return an open
`SQLiteSnapshotStore` owned by the caller.

## Store Protocol

The backend-neutral `SnapshotStore` protocol is exported from
`snapshotfs.stores`. Its lookup names are bytes:

```python
from snapshotfs.stores import SnapshotStore

node = store.lookup(parent_inode=1, name=b"C")
```

## Public Package

```{eval-rst}
.. automodule:: snapshotfs
   :members:
   :imported-members:
   :undoc-members:
   :member-order: bysource
```

## Secondary Modules

The extension contracts and less common types are exported from:

- `snapshotfs.model`, including `ContentStatus`;
- `snapshotfs.parsers`, including `ParseResult`;
- `snapshotfs.sources`;
- `snapshotfs.stores`, including memory-store and builder types;
- `snapshotfs.cli_registry`, for programmatic CLI extensions.
