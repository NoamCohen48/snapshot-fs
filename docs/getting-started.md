# Getting Started

SnapshotFS requires Python 3.12 or newer. This guide uses
[uv](https://docs.astral.sh/uv/) to run the project from a checkout.

## Install

```bash
uv sync --all-groups
```

Mount support is optional and Linux-only. On Debian or Ubuntu:

```bash
sudo apt install fuse3 libfuse3-dev pkg-config
uv sync --all-groups --extra fuse
```

## Create A Listing

The built-in parser accepts the English output of Windows `dir /s`. Generate a
listing on the filesystem you want to inventory:

```batch
dir C:\Path\To\Inventory /s > listing.txt
```

The encoding and date order depend on the Windows environment that produced the
file. SnapshotFS does not guess either setting.

## Create A Snapshot

```bash
uv run snapshotfs sqlite create backup.snapshot \
  --source file listing.txt \
  --parser windows-dir \
  --encoding cp1252 \
  --date-format mdy
```

The command validates the complete listing and publishes `backup.snapshot` only
after a successful import. It will not replace an existing artifact unless
`--overwrite` is supplied.

## Inspect It

Print the imported hierarchy:

```bash
uv run snapshotfs sqlite show backup.snapshot
```

Produce structured output for another program:

```bash
uv run snapshotfs sqlite show backup.snapshot --json
```

Continue with the [CLI guide](cli/index.md) or use the same pipeline through the
[Python library](library/index.md).
