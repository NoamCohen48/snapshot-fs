# In-Memory Commands

[Command-line guide](index.md)

Use an in-memory store when a listing should be mounted without creating a
persistent artifact:

```bash
mkdir -p /tmp/snapshotfs
uv run --extra fuse snapshotfs memory mount /tmp/snapshotfs \
  --source file listing.txt \
  --parser windows-dir
```

The listing is parsed and validated before the mount becomes available. The
store exists only for the lifetime of the command, and the command blocks until
the mount is interrupted or externally unmounted.

Parser options follow the component selections:

```bash
uv run --extra fuse snapshotfs memory mount /tmp/snapshotfs \
  --source file listing.txt \
  --parser windows-dir \
  --encoding utf-16 \
  --date-format ymd
```

Use a [SQLite artifact](sqlite.md) when the import should be reusable or
inspectable without mounting.
