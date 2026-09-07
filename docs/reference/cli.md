# CLI Reference

[Documentation](../index.md)

This file is generated from the built-in Click command tree. The
create and memory-mount help is rendered with the built-in source and parser
selected so their contextual parameters are included.

Regenerate it with `uv run python scripts/generate_cli_reference.py`.

## Root Command

`snapshotfs --help`

```text
Usage: snapshotfs [OPTIONS] COMMAND [ARGS]...

  Create and mount filesystem snapshots.

Options:
  --help  Show this message and exit.

Commands:
  completion  Print shell completion registration code.
  memory      Build transient in-memory stores.
  sqlite      Create, mount, and display SQLite stores.
```

## SQLite Commands

`snapshotfs sqlite --help`

```text
Usage: snapshotfs sqlite [OPTIONS] COMMAND [ARGS]...

  Create, mount, and display SQLite stores.

Options:
  --help  Show this message and exit.

Commands:
  create  Parse a source into a persistent SQLite store.
  mount   Mount an existing SQLite store read-only.
  show    Display an existing SQLite store.
```

## SQLite Create

`snapshotfs sqlite create --source file --parser windows-dir --help`

```text
Usage: snapshotfs sqlite create [OPTIONS] OUTPUT INPUT

  Parse a source into a persistent SQLite store.

Options:
  --source [file]              Source implementation used to read the listing.
                               [required]
  --parser [windows-dir]       Parser implementation used to interpret the listing.
                               [required]
  --overwrite
  --mount PATH                 Mount the new store immediately at this path.
  --simulate-missing-content   Return NUL stand-ins for declared missing file content.
  --help                       Show this message and exit.
  --encoding TEXT              [default: utf-8]
  --date-format [mdy|dmy|ymd]  [default: mdy]
```

## SQLite Mount

`snapshotfs sqlite mount --help`

```text
Usage: snapshotfs sqlite mount [OPTIONS] SNAPSHOT MOUNTPOINT

  Mount an existing SQLite store read-only.

Options:
  --simulate-missing-content  Return NUL stand-ins for declared missing file content.
  --help                      Show this message and exit.
```

## SQLite Show

`snapshotfs sqlite show --help`

```text
Usage: snapshotfs sqlite show [OPTIONS] SNAPSHOT

  Display an existing SQLite store.

Options:
  --json
  --help  Show this message and exit.
```

## Memory Commands

`snapshotfs memory --help`

```text
Usage: snapshotfs memory [OPTIONS] COMMAND [ARGS]...

  Build transient in-memory stores.

Options:
  --help  Show this message and exit.

Commands:
  mount  Parse a source and mount it from memory.
```

## Memory Mount

`snapshotfs memory mount --source file --parser windows-dir --help`

```text
Usage: snapshotfs memory mount [OPTIONS] MOUNTPOINT INPUT

  Parse a source and mount it from memory.

Options:
  --source [file]              Source implementation used to read the listing.
                               [required]
  --parser [windows-dir]       Parser implementation used to interpret the listing.
                               [required]
  --simulate-missing-content   Return NUL stand-ins for declared missing file content.
  --help                       Show this message and exit.
  --encoding TEXT              [default: utf-8]
  --date-format [mdy|dmy|ymd]  [default: mdy]
```

## Completion

`snapshotfs completion --help`

```text
Usage: snapshotfs completion [OPTIONS] {bash|zsh|fish}

  Print shell completion registration code.

Options:
  --help  Show this message and exit.
```
