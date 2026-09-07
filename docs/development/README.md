# Development

SnapshotFS is organized around independent boundaries. Input acquisition,
parsing, snapshot storage, and filesystem exposure communicate through narrow
protocols, allowing a component to change without changing the entire pipeline.

## Documentation Map

- [Setup and checks](setup.md): prepare an environment and run project checks.
- [Documentation](documentation.md): understand, build, and update the
  documentation site and generated references.
- [Entrypoints](entrypoints.md): the CLI, public library API, and component
  registry.
- [Source](components/source.md): acquire binary input streams.
- [Parser](components/parser.md): turn a stream into entries and diagnostics.
- [Store](components/store.md): validate, normalize, and expose a snapshot.
- [Adapter](components/adapter.md): expose a store as a read-only filesystem.

## Data Flow

```text
CLI or library API
        |
        v
Source -> Parser -> import service -> builder/store -> adapter
```

The parser yields `ParsedEntry` values and diagnostics while the import service
feeds entries to a store builder. Builders normalize and validate the tree. A
successful import returns an immutable store; a failed import exposes no partial
snapshot. Adapters only consume normalized store data and do not inspect source
formats.

## Package Layout

```text
src/snapshotfs/
  api.py                 Public composition API
  cli.py                 Command-line entry point
  cli_registry.py        CLI component registrations
  import_service.py      Import orchestration
  model/                 Immutable domain objects
  sources/               Input acquisition components
  parsers/               Input-format components
  stores/                Snapshot backends and builders
  fuse/adapter/          Read-only filesystem adapter
tests/                   Unit and integration tests
```

For model, artifact, parser, and filesystem invariants, see the detailed
[architecture notes](../architecture.md).
