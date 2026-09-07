# Mounting A Store

[Python library](index.md)

`mount_store()` exposes an already imported store as a read-only filesystem:

```python
from snapshotfs import mount_store, open_sqlite_store

with open_sqlite_store("backup.snapshot") as store:
    mount_store(store, "/tmp/snapshotfs")
```

The call blocks until interrupted or externally unmounted. It does not close the
store, so the caller must keep a SQLite store open for the complete mount
lifetime.

Mounting requires Linux, libfuse 3, a usable `/dev/fuse`, suitable permissions,
and the optional `fuse` dependencies. If `pyfuse3` or Trio is missing,
`mount_store()` raises `FuseUnavailableError`.

The mounted filesystem is strictly read-only. Directories use mode `0555`, files
use `0444`, and write-capable operations fail with `EROFS`. Each node exposes its
content state through the `user.snapshotfs.content_status` extended attribute.

Pass `simulate_missing_content=True` only when zero-filled stand-in data is
acceptable. The [missing content guide](../concepts/missing-content.md) explains
which files are simulated and why the default is `ENODATA`.
