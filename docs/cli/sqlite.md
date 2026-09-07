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

The command blocks until interrupted or externally unmounted. SnapshotFS has no
unmount command; on Linux use:

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
