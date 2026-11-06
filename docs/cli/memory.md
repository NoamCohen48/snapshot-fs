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
store exists only for the lifetime of the command, and in foreground mode the command blocks until
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

Add `--background` to mount without holding the terminal, then run
`snapshotfs unmount MOUNTPOINT` to stop it. The worker retains the in-memory
store until unmount; no persistent artifact is created. The command returns
only after readiness and reports startup errors. `--foreground` is the default.
See [mount modes](sqlite.md#three-mount-modes) for lifecycle and timeout details.
