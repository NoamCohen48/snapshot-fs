# Entrypoints

[Development](README.md)

SnapshotFS has a command-line entry point and a small public library API. Both
compose the same source, parser, store, and adapter boundaries.

## Command-Line Interface

The `snapshotfs` command is declared in `pyproject.toml` and calls
`snapshotfs.cli:main`. The CLI is organized into store-owned command groups.
SQLite provides `create`, `mount`, and `show`; memory provides `mount`.

Commands that read an input require explicit `--source` and `--parser`
selections. The CLI does not probe the input or choose components on behalf of
the user.

`CLIRegistry` in `cli_registry.py` maps component names to factories and Click
parameters. A component command identifies the selected source and parser,
then installs parameters from that pair only. This avoids arguments from
unrelated components becoming required or conflicting.

Stores register a top-level command group with `StoreCLIRegistration`. The
group owns its actions and backend-specific configuration, so adding an HTTP
store does not require modifying root dispatch logic. Store domain types remain
independent of Click; only their CLI adapters construct command groups.

## Library API

`snapshotfs.api` contains the public composition functions and re-exports them
from `snapshotfs`:

- `create_memory_store(source, parser)` imports a transient snapshot.
- `create_sqlite_store(source, parser, destination)` imports a persistent
  snapshot artifact.
- `open_sqlite_store(destination)` opens a persistent artifact.
- `mount_store(store, mountpoint)` mounts an already imported snapshot.

Keep new public composition operations in `api.py`. Avoid importing optional
adapter dependencies at package import time; `mount_store` loads the adapter
lazily and reports a clear error when it is unavailable.

## CLI Components

To make a new source or parser available from the CLI, add a typed registration
in `cli_registry.py`. A registration owns its name, factory, and Click
parameters. The factory receives parsed command arguments and returns an object
that implements the corresponding protocol.

To add a store CLI, register a unique name and a command-group factory. The
factory may provide whichever actions make sense for that store, such as
`create`, `mount`, `show`, or backend-specific maintenance commands. It can use
`CLIRegistry.component_command` when an action imports through a registered
source and parser.

Do not add automatic format detection. Explicit component selection keeps the
CLI predictable and allows registrations to reuse options when they are never
selected together.
