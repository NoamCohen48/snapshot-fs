# Python API Reference

[Documentation](../index.md)

The public API is divided by responsibility. Import sources, parsers, store
backends, models, and mounting operations from their corresponding modules.

## Composition

```python
from snapshotfs.fuse import mount_store
from snapshotfs.store.memory import create_memory_store
from snapshotfs.store.sqlite import create_sqlite_store, open_sqlite_store
```

`create_memory_store()` returns an `InMemorySnapshotStore`.
`create_sqlite_store()` and `open_sqlite_store()` return an open
`SQLiteSnapshotStore` owned by the caller.

## Store Protocol

The backend-neutral `SnapshotStore` protocol is exported from
`snapshotfs.store`. Its lookup names are bytes:

```python
from snapshotfs.store import SnapshotStore

node = store.lookup(parent_inode=1, name=b"C")
```

```{eval-rst}
.. automodule:: snapshotfs.store
   :members:
   :imported-members:
   :undoc-members:
   :member-order: bysource
```

## Sources

```{eval-rst}
.. automodule:: snapshotfs.source
   :members:
   :imported-members:
   :undoc-members:
   :member-order: bysource
```

## Parsers

```{eval-rst}
.. automodule:: snapshotfs.parser
   :members:
   :imported-members:
   :undoc-members:
   :member-order: bysource
```

## Memory Stores

```{eval-rst}
.. automodule:: snapshotfs.store.memory
   :members:
   :imported-members:
   :undoc-members:
   :member-order: bysource
```

## SQLite Stores

```{eval-rst}
.. automodule:: snapshotfs.store.sqlite
   :members:
   :imported-members:
   :undoc-members:
   :member-order: bysource
```

## Mounting

```{eval-rst}
.. automodule:: snapshotfs.fuse
   :members: FuseUnavailableError, mount_store
   :imported-members:
   :undoc-members:
   :member-order: bysource
```

## Models

```{eval-rst}
.. automodule:: snapshotfs.model
   :members:
   :imported-members:
   :undoc-members:
   :member-order: bysource
```

The programmatic CLI extension API remains in `snapshotfs.cli_registry`.
