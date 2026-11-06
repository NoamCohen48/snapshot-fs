# SQLite Commands

[Command-line guide](index.md)

SQLite artifacts preserve an imported snapshot so it can be inspected or
mounted later without reparsing the source listing.

## Create

```bash
snapshotfs sqlite create backup.snapshot \
  --source file listing.txt \
  --parser windows-dir
```

Use the parser settings that match the environment which produced the listing:

```bash
snapshotfs sqlite create backup.snapshot \
  --source file listing.txt \
  --parser windows-dir \
  --encoding cp1252 \
  --date-format dmy
```

The defaults are UTF-8 and month-day-year (`mdy`). Accepted date formats are
`mdy`, `dmy`, and `ymd`.

An existing output is preserved by default. Replace it atomically with:

```bash
snapshotfs sqlite create backup.snapshot \
  --source file listing.txt \
  --parser windows-dir \
  --overwrite
```

## Show

```bash
snapshotfs sqlite show backup.snapshot
snapshotfs sqlite show backup.snapshot --json
```

The human-readable form prints `/`, descendants indented by two spaces, and a
trailing `/` on directories. The JSON form is documented in the
[JSON output reference](../reference/json-output.md).

## Mount

```bash
mkdir -p /tmp/snapshotfs
uv run --extra fuse snapshotfs sqlite mount \
  backup.snapshot /tmp/snapshotfs
```

In foreground mode, the command blocks until interrupted or externally
unmounted. Run `snapshotfs unmount /tmp/snapshotfs` from another terminal,
or use the system helper:

```bash
fusermount3 -u /tmp/snapshotfs
```

Create and mount in one operation with `--mount`:

```bash
uv run --extra fuse snapshotfs sqlite create backup.snapshot \
  --source file listing.txt \
  --parser windows-dir \
  --mount /tmp/snapshotfs
```

`--simulate-missing-content` is valid on `sqlite create` only when `--mount` is
also present. See [missing file content](../concepts/missing-content.md) before
enabling it.

## Three Mount Modes

Foreground remains the default; `--foreground` makes it explicit. The command
holds the terminal until Ctrl-C or an external unmount:

```bash
snapshotfs sqlite mount backup.snapshot /tmp/snapshotfs --foreground
```

Background mode returns only after the filesystem is mounted and ready. The
worker detaches from the terminal; diagnostics continue in the rotating log:

```bash
snapshotfs sqlite mount backup.snapshot /tmp/snapshotfs --background
snapshotfs unmount /tmp/snapshotfs
```

Both commands are one-shot. The mountpoint must already exist and be empty.
`unmount` verifies that the path is a SnapshotFS mount before invoking
`fusermount3`. It reports busy mounts rather than forcefully or lazily detaching
them; close programs using the mount and retry. Background startup waits up to
120 seconds; adjust `--startup-timeout SECONDS` for large imports. A startup
failure is reported to the caller, not treated as a successful background job.

`sqlite create --mount PATH --background` imports and mounts in the worker;
`--background` without `--mount` is rejected. A valid artifact remains available
if its subsequent mount fails. Background re-execution uses the built-in CLI
registry; custom in-process registry factories require foreground mode.

For a command-scoped mount, pass a program after `--`:

```bash
snapshotfs run backup.snapshot -- find '{mountpoint}' -type f
snapshotfs run backup.snapshot --simulate-missing-content -- some-program '{mountpoint}'
```

SnapshotFS creates a temporary mountpoint, waits for readiness, substitutes
`{mountpoint}` inside command arguments, runs the program, then unmounts and
removes the temporary directory. It also supplies the path through the
`SNAPSHOTFS_MOUNTPOINT` environment variable. Arguments are passed directly to
the program; no shell is invoked implicitly. The program's exit status is
preserved (`128 + signal` when terminated by a signal), and Ctrl-C stops the
program and cleans up the mount. Cleanup is also attempted when the program
cannot start. Do not leave background descendants holding the mount open.

`run` currently takes an existing SQLite artifact. Use `memory mount` when you
want to mount a listing directly. All three modes require Linux and FUSE access.
