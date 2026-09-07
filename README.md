<p align="center">
  <img src="assets/snapshotfs.svg" width="112" alt="SnapshotFS icon">
</p>

<h1 align="center">SnapshotFS</h1>

<p align="center">
  <a href="#getting-started">Getting Started</a> | <a href="docs/index.md">Documentation</a> | <a href="docs/development/">Development</a> | <a href="docs/architecture.md">Architecture</a>
</p>

**A composable toolkit for turning filesystem listings into validated,
read-only snapshots.** Inspect an inventory, preserve it as an artifact, or
mount it as a filesystem. A snapshot contains metadata; non-empty file content
is unavailable unless supplied separately.

| Capability | Description |
| --- | --- |
| Extensible pipeline | Add sources, parsers, stores, and adapters without changing unrelated components. |
| Validated snapshots | Reject invalid entries and unsafe paths before a snapshot is available. |
| Explicit composition | Select the source and parser intentionally; SnapshotFS does not guess formats. |
| Read-only access | Inspect snapshots through the CLI, library API, or a filesystem mount on supported platforms. |

---

## Requirements

- Python 3.12 or newer.
- Linux, libfuse 3, and the optional `fuse` extra to mount snapshots.

## Installation

The commands below use [uv](https://docs.astral.sh/uv/). Clone the repository
and create the project environment:

```bash
uv sync --all-groups
```

For mount support on Debian or Ubuntu, install the system dependency and the
optional Python dependencies:

```bash
sudo apt install fuse3 libfuse3-dev pkg-config
uv sync --all-groups --extra fuse
```

## Getting Started

### Command-Line Usage

The CLI is organized by store type. Every command that reads a listing requires
an explicit source and parser. Selecting them also enables their configuration
options; use `snapshotfs sqlite create --source file INPUT --parser
windows-dir --help` to see the complete contextual help.

Create a durable SQLite artifact, then display it without reparsing the listing:

```bash
uv run snapshotfs sqlite create backup.snapshot \
  --source file listing.txt --parser windows-dir \
  --encoding cp1252 --date-format mdy
uv run snapshotfs sqlite show backup.snapshot --json
```

`sqlite create` will not replace an existing artifact unless `--overwrite` is
passed.

#### Mount A Snapshot

Mount directly from a listing:

```bash
mkdir -p /tmp/snapshotfs
uv run --extra fuse snapshotfs memory mount /tmp/snapshotfs \
  --source file listing.txt --parser windows-dir
```

Or mount a previously imported artifact:

```bash
uv run --extra fuse snapshotfs sqlite mount backup.snapshot /tmp/snapshotfs
```

Create a persistent store and mount it immediately in one command:

```bash
uv run --extra fuse snapshotfs sqlite create backup.snapshot \
  --source file listing.txt --parser windows-dir --mount /tmp/snapshotfs
```

The mount runs until interrupted with Ctrl-C. If necessary, unmount it with
`fusermount3 -u /tmp/snapshotfs`.

Listings do not include file bytes. Reads of non-empty files return `ENODATA` by
default. Use `--simulate-missing-content` only when zero-filled stand-in data is
appropriate for the consumer.

#### Shell Completion

Enable completion in the current shell session:

```bash
# Bash
eval "$(snapshotfs completion bash)"

# Zsh
eval "$(snapshotfs completion zsh)"

# Fish
snapshotfs completion fish | source
```

### Library Usage

Compose a source and parser explicitly, create a snapshot, then mount it. This
requires Linux and the `fuse` extra:

```python
from snapshotfs import (
    FileSource,
    WindowsDirParser,
    create_memory_store,
    mount_store,
)

source = FileSource("listing.txt")
parser = WindowsDirParser(encoding="cp1252", date_format="mdy")
store = create_memory_store(source, parser)
mount_store(store, "/tmp/snapshotfs")
```

`mount_store` blocks until the filesystem is unmounted. Pass
`simulate_missing_content=True` to opt into zero-filled stand-ins for listed
files whose contents are unavailable.

## Development

See the [full documentation](docs/index.md) for the CLI and Python library.
See [Development](docs/development/) for the project layout, component
boundaries, extension guidance, and quality-check commands. The detailed
[architecture notes](docs/architecture.md) document the format and storage
invariants.
