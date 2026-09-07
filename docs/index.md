# SnapshotFS Documentation

SnapshotFS imports filesystem listings into validated, immutable snapshots. A
snapshot can be inspected through Python or the command line, persisted as a
SQLite artifact, or mounted as a read-only filesystem on Linux.

SnapshotFS stores the metadata present in a listing. It does not recover the
bytes of non-empty files unless content is supplied separately.

## Start Here

- [Getting started](getting-started.md) walks through creating and inspecting a
  snapshot.
- [Command-line guide](cli/index.md) documents commands, output, completion, and
  common failures.
- [Library guide](library/index.md) explains the Python API and store lifecycle.
- [Snapshot concepts](concepts/snapshots.md) describes the data model and its
  guarantees.

```{toctree}
:maxdepth: 2
:hidden:

getting-started
cli/index
cli/sqlite
cli/memory
cli/completion
cli/troubleshooting
library/index
library/importing
library/stores
library/parsers-and-sources
library/mounting
library/error-handling
concepts/snapshots
concepts/filesystem-listings
concepts/missing-content
reference/api
reference/cli
reference/json-output
reference/sqlite-artifact
development/README
development/setup
development/documentation
development/entrypoints
development/components/source
development/components/parser
development/components/store
development/components/adapter
architecture
implementation-plan
publishing
```

## Reference

- [Python API](reference/api.md)
- [Complete CLI help](reference/cli.md)
- [JSON output](reference/json-output.md)
- [SQLite artifacts](reference/sqlite-artifact.md)

## Project Documentation

- [Development](development/README.md)
- [Architecture](architecture.md)
- [Implementation plan](implementation-plan.md)
- [Publishing this site](publishing.md)
