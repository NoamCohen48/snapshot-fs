# SnapshotFS

SnapshotFS includes a parser for native English Windows `dir /s` listings and
builds an immutable in-memory representation or a persistent SQLite artifact.
Its parser boundary uses platform-neutral path components, allowing Linux,
macOS, archive, object-store, and custom namespace parsers to use either backend.
Stores can be inspected or mounted read-only on Linux.

```bash
uv sync --all-groups
uv run snapshotfs inspect listing.txt --source file --parser windows-dir
uv run snapshotfs inspect listing.txt --source file --parser windows-dir \
  --encoding cp1252 --json
uv run snapshotfs import backup.snapshot listing.txt \
  --source file --parser windows-dir
uv run snapshotfs inspect-store backup.snapshot --json
```

Mount support requires libfuse 3 and the optional project extra. On Debian or
Ubuntu:

```bash
sudo apt install fuse3 libfuse3-dev pkg-config
uv sync --all-groups --extra fuse
mkdir -p /tmp/snapshotfs
uv run --extra fuse snapshotfs mount listing.txt /tmp/snapshotfs \
  --source file --parser windows-dir
```

The mount runs until interrupted with Ctrl-C. If cleanup is needed, run
`fusermount3 -u /tmp/snapshotfs`.

Persisted artifacts can be reopened and mounted without parsing the source:

```bash
uv run --extra fuse snapshotfs mount-store backup.snapshot /tmp/snapshotfs
```

`snapshotfs import` refuses an existing output by default. Its atomic hard-link
publication is race-safe: concurrent no-overwrite imports cannot replace or
delete the winner. Pass `--overwrite` to use atomic replacement; concurrent
overwrite imports deliberately use last-finisher-wins semantics because a
portable filesystem compare-and-swap is unavailable. Imports are built in a
temporary sibling database. Parse and validation failures leave an existing
output untouched. Temporary database and sidecar cleanup is best effort, so an
OS cleanup failure may leave an unpublished temporary file but never masks the
original import error.

Publication fsyncs the database and, on hosts that support directory file
descriptors, the destination directory. If directory fsync fails,
`SQLiteDurabilityError` is raised, but the atomic namespace operation has
already happened and the destination may contain the new artifact. Similarly,
a rare failure removing the temporary hard link after no-overwrite publication
raises `SQLitePublicationError`; the destination is never blindly unlinked.
An artifact contains exactly one snapshot, uses inode 1 for its root, and is
schema-version checked whenever it is opened.

Non-empty files contain metadata only and return `ENODATA` by default. Explicit
simulation returns bounded NUL stand-ins without claiming they are source data:

```bash
uv run --extra fuse snapshotfs mount listing.txt /tmp/snapshotfs \
  --source file --parser windows-dir \
  --simulate-missing-content
```

SnapshotFS is also a library. Sources and parsers are always selected
explicitly; there is no format probing or automatic detection:

```python
from snapshotfs import FileSource, WindowsDirParser, create_memory_store, mount_store

source = FileSource("listing.txt")
parser = WindowsDirParser(encoding="utf-8", date_format="mdy")
store = create_memory_store(source, parser)
mount_store(store, "/tmp/snapshotfs", simulate_missing_content=True)
```

To inspect or transform the normalized snapshot without mounting it:

```python
from snapshotfs import FileSource, WindowsDirParser, create_memory_store

store = create_memory_store(FileSource("listing.txt"), WindowsDirParser())
for node in store.iter_nodes():
    print(node)
```

To create and reopen a SQLite-backed store:

```python
from snapshotfs import (
    FileSource,
    WindowsDirParser,
    create_sqlite_store,
    open_sqlite_store,
)

with create_sqlite_store(
    FileSource("listing.txt"),
    WindowsDirParser(),
    "backup.snapshot",
) as store:
    print(store.get_root(next(iter(store.iter_nodes())).snapshot_id))

with open_sqlite_store("backup.snapshot") as store:
    for node in store.iter_nodes():
        print(node)
```

SQLite stores own a database connection. Close them explicitly or use the
context manager as above; reads after close raise `SQLiteStoreClosedError`.
Snapshot and node metadata is deeply immutable in both backends and is stored
as JSON, never pickle. Values must consist of JSON objects with string keys,
arrays, strings, finite numbers, booleans, and null; unsupported values are
rejected before either backend builds a store.

SQLite artifacts require `STRICT` tables. Opening validates storage classes,
the exact version-4 table/column/primary-key/foreign-key/unique/index contract,
integer ranges, the complete root-connected acyclic directory graph, parent
kinds, snapshot association, UTF-8 mounted names,
enums, content invariants, diagnostics, timestamps, and metadata before the
store is exposed. Non-root `.` and `..` names are invalid. Validation checks
content type and length in SQL without loading content BLOBs. Public reads and
`close()` are serialized by an internal reentrant lock; a close race either
completes the read or raises `SQLiteStoreClosedError`, never a raw SQLite
exception.

Mounted components are limited to 255 UTF-8 bytes during shared normalization,
so memory and SQLite imports fail identically with source-line context before
publication. Reopen validation independently enforces the limit against
malicious artifacts.

Custom parsers assign each `ParsedEntry` a tuple of path components relative to
SnapshotFS's virtual mount root:

```python
from snapshotfs import NodeKind, Observation, ParsedEntry

linux_file = ParsedEntry(
    ("usr", "local", "bin", "tool"),
    NodeKind.FILE,
    Observation.FILE_ENTRY,
    size=42,
    modified_local=None,
)

windows_path = ("C", "Users", "Alice", "file.txt")
```

Parsers own source syntax, separators, and roots. Generic stores never interpret
drive letters, backslashes, URI syntax, or host paths. Paths are exact and
case-sensitive.
Mounted components are Unicode names encoded as UTF-8; each must be non-empty,
must not be `.` or `..`, and cannot contain NUL or `/`.

## CLI Extensibility

The CLI still requires explicit `--source` and `--parser` selections and never
probes input. It first parses those selectors, then builds the full parser using
only the two selected registrations. Embedders can provide a typed registry;
each registration owns its factory and every argparse argument needed to
construct the component, including any positional input:

```python
from snapshotfs.cli import main
from snapshotfs.cli_registry import CLIRegistry, ParserRegistration, SourceRegistration

registry = CLIRegistry(
    sources=[SourceRegistration("remote", make_remote_source, add_remote_options)],
    parsers=[ParserRegistration("custom", make_custom_parser, add_custom_options)],
)
status = main(
    ["inspect", "snapshot", "--source", "remote", "--parser", "custom"],
    registry,
)
```

The registry names automatically become argparse choices and shell-completion
suggestions. Once selectors are present, completion also includes the selected
components' flags and values. Required options on unselected registrations do
not apply, and registrations may reuse argument names unless that source and
parser are selected together. Duplicate names and conflicts within the selected
pair or with command-owned arguments are rejected clearly. Partial selector
values remain completion candidates; only exact registered names activate a
component's arguments. The built-in `default_registry()` registers `file` and
`windows-dir`; adding another implementation does not require changing CLI
dispatch.

## Shell Completion

SnapshotFS completes subcommands, flags, paths, source names, parser names,
encodings, and date formats through argcomplete. Enable it for the current Bash
or Zsh session:

```bash
eval "$(snapshotfs completion bash)"
eval "$(snapshotfs completion zsh)"
```

To enable completion permanently, add the command for your shell and reload its
configuration:

```bash
# Bash
printf '%s\n' 'eval "$(snapshotfs completion bash)"' >> ~/.bashrc
source ~/.bashrc

# Zsh
printf '%s\n' 'eval "$(snapshotfs completion zsh)"' >> ~/.zshrc
source ~/.zshrc
```

Run only the Bash or Zsh pair that matches your shell.
