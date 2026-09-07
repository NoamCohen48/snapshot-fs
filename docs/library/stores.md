# Reading Stores

[Python library](index.md)

Both built-in backends implement `snapshotfs.stores.SnapshotStore`:

```python
root = store.get_node(1)
drive = store.lookup(root.id, b"C")

if drive is not None:
    for child in store.iter_children(drive.id):
        print(child.mounted_name.decode("utf-8"))
```

Mounted names are UTF-8 `bytes`, not strings. Children are sorted by exact
bytewise mounted name, and lookup is case-sensitive.

The store interface provides:

- `get_snapshot(snapshot_id)`
- `get_root(snapshot_id)`
- `get_node(inode)`
- `lookup(parent_inode, name)`
- `iter_children(parent_inode, offset=0)`
- `iter_nodes()`
- `diagnostics` and `diagnostic_count`

## Memory Lifecycle

`create_memory_store()` returns an immutable `InMemorySnapshotStore`. It is not
a context manager and has no `close()` method. Ordinary Python references control
its lifetime.

## SQLite Lifecycle

SQLite stores hold a database connection and should be used as context managers:

```python
from snapshotfs import open_sqlite_store

with open_sqlite_store("backup.snapshot") as store:
    nodes = tuple(store.iter_nodes())
```

`close()` is idempotent. Reads after closing raise `SQLiteStoreClosedError`.
Opening an artifact is read-only and validates its schema, integrity, storage
types, snapshot count, root, and tree reachability before returning a store.
