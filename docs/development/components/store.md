# Store

[Development](../README.md) / Store

A store exposes a normalized, immutable snapshot. Builders receive parser
entries during import, validate them, and produce the store only after a
successful import.

## Contract

`SnapshotStore` in `snapshotfs.stores.base` provides the lookup and traversal
operations shared by storage backends:

```python
class SnapshotStore(Protocol):
    diagnostics: tuple[ImportDiagnostic, ...]
    diagnostic_count: int

    def get_snapshot(self, snapshot_id: str) -> Snapshot: ...
    def get_root(self, snapshot_id: str) -> Node: ...
    def get_node(self, inode: int) -> Node: ...
    def lookup(self, parent_inode: int, name: bytes) -> Node | None: ...
    def iter_children(self, parent_inode: int, offset: int = 0) -> Iterable[Node]: ...
    def iter_nodes(self) -> Iterable[Node]: ...
```

## Import And Normalization

`import_service.py` coordinates imports. It creates snapshot metadata, keeps the
source stream open while parser entries are consumed, and converts parser or
builder errors into `ImportFailure`.

Builders are responsible for normalized tree invariants. They validate mounted
path components, synthesize missing directories, merge compatible observations,
and reject conflicts. If parsing or building fails, no partial store is returned.

## Backends

The project supplies transient and persistent backends behind the same contract.
Persistent stores own external resources and must define their close and
context-manager behavior. Both backends must preserve the same observable path,
node, diagnostic, and traversal semantics.

When adding or changing a backend, test it against the shared store behavior and
against hostile or malformed persisted data where applicable.
