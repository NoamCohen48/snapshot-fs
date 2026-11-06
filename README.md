<p align="center">
  <img src="assets/snapshotfs.svg" width="112" alt="SnapshotFS icon">
</p>

<h1 align="center">SnapshotFS</h1>

<p align="center">
  <a href="#getting-started">Getting Started</a> | <a href="docs/index.md">Documentation</a> | <a href="docs/development/">Development</a> | <a href="docs/architecture.md">Architecture</a>
</p>

**Mount filesystem listings as validated, read-only FUSE filesystems.**
Browse an offline inventory with ordinary filesystem tools, or preserve it as
a portable SQLite artifact and mount it later. A snapshot contains metadata; non-empty file content
is unavailable unless supplied separately.

| Capability | Description |
| --- | --- |
| Extensible pipeline | Add sources, parsers, stores, and adapters without changing unrelated components. |
| Validated snapshots | Reject invalid entries and unsafe paths before a snapshot is available. |
| Explicit composition | Select the source and parser intentionally; SnapshotFS does not guess formats. |
| Read-only access | Inspect snapshots through the CLI, library API, or a filesystem mount on supported platforms. |

---

## Quick Start: Mount On Linux

Install a release package (adjust the version):

```bash
# Debian / Ubuntu, x86-64
sudo apt install ./snapshotfs_0.1.0_amd64.deb
# Or Arch Linux, x86-64
sudo pacman -U ./snapshotfs-0.1.0-1-x86_64.pkg.tar.zst
```

Both include Python and its FUSE bindings and depend on the system `fuse3`
package. Mount the included sample:

```bash
mkdir -p /tmp/snapshotfs-demo
snapshotfs memory mount /tmp/snapshotfs-demo \
  --source file /usr/share/doc/snapshotfs/examples/windows-dir.txt \
  --parser windows-dir --encoding utf-8 --date-format mdy
```

In another terminal, run `ls -l /tmp/snapshotfs-demo/C/Users/Alice` or browse
with your file manager. Stop with Ctrl-C or
`fusermount3 -u /tmp/snapshotfs-demo`.

Names and metadata are available; original file contents are absent. Non-empty
file reads return `ENODATA`. The optional `--simulate-missing-content` mount
flag supplies zero-filled placeholders, not original content.

See the [complete mounting quickstart](docs/getting-started.md).

## Requirements

- Mounting: Linux, FUSE 3, access to `/dev/fuse`, and an empty mountpoint.
- Linux release packages and CLI binaries bundle Python and FUSE bindings.
- Wheel/source installation: Python 3.12 or newer, plus the `fuse` extra to mount.
- macOS and Windows binaries support import/inspection; mounting is Linux-only.

## Installation

The commands below use [uv](https://docs.astral.sh/uv/). Clone the repository
and create the project environment:

```bash
uv sync --all-groups
```

Release downloads support both Python tool installation and standalone execution.
Download the `.whl` from GitHub Releases, then choose one:

```bash
# Install the CLI into an isolated environment
pipx install ./snapshotfs-0.1.0-py3-none-any.whl
snapshotfs --help

# Or run the CLI without a permanent installation
uvx --from ./snapshotfs-0.1.0-py3-none-any.whl snapshotfs --help

# Install the SDK (also installs the CLI entry point)
python -m pip install ./snapshotfs-0.1.0-py3-none-any.whl
```

Adjust the wheel filename for the downloaded version. Alternatively, extract the
CLI `.tgz` for your platform and run its `snapshotfs` executable directly
(`snapshotfs.exe` on Windows). Standalone binaries do not require Python.

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
from snapshotfs.fuse import mount_store
from snapshotfs.parser import WindowsDirParser
from snapshotfs.source import FileSource
from snapshotfs.store.memory import create_memory_store

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

## Release downloads

GitHub releases provide standalone CLI archives for Linux, macOS, and Windows,
an SDK wheel and source distribution, and offline HTML documentation. See
[Publishing](docs/publishing.md#github-releases) for platform support and the
release process.

## Troubleshooting

Run `snapshotfs doctor --mountpoint /path/to/mount` to check FUSE setup and
`snapshotfs --version` to identify the installed build. Commands automatically
write a rotating diagnostic log; on Linux it defaults to
`~/.local/state/snapshotfs/snapshotfs.log` (or `$XDG_STATE_HOME/snapshotfs/`).
Use global options before the command for detailed troubleshooting:

```bash
snapshotfs -v --log-file ./snapshotfs-debug.log sqlite mount backup.snapshot /tmp/snapshotfs
```

See [troubleshooting](docs/cli/troubleshooting.md) for setup checks, import
error hints, and log locations.
