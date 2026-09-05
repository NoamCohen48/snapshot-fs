"""Immutable in-memory snapshot store."""

from collections.abc import Iterable, Mapping

from snapshotfs.diagnostics import ImportDiagnostic
from snapshotfs.model import Node, Snapshot


class InMemorySnapshotStore:
    def __init__(
        self,
        snapshot: Snapshot,
        nodes: Mapping[int, Node],
        children: Mapping[int, Mapping[bytes, int]],
        diagnostics: tuple[ImportDiagnostic, ...],
        diagnostic_count: int,
    ) -> None:
        self._snapshot = snapshot
        self._nodes = nodes
        self._children = children
        self._diagnostics = tuple(diagnostics)
        self._diagnostic_count = diagnostic_count

    @property
    def diagnostics(self) -> tuple[ImportDiagnostic, ...]:
        return self._diagnostics

    @property
    def diagnostic_count(self) -> int:
        return self._diagnostic_count

    def get_snapshot(self, snapshot_id: str) -> Snapshot:
        if snapshot_id != self._snapshot.id:
            raise KeyError(snapshot_id)
        return self._snapshot

    def get_root(self, snapshot_id: str) -> Node:
        self.get_snapshot(snapshot_id)
        return self._nodes[1]

    def get_node(self, inode: int) -> Node:
        return self._nodes[inode]

    def lookup(self, parent_inode: int, name: bytes) -> Node | None:
        node_id = self._children[parent_inode].get(name)
        return self._nodes[node_id] if node_id is not None else None

    def iter_children(self, parent_inode: int, offset: int = 0) -> Iterable[Node]:
        node_ids = self._children[parent_inode]
        names = sorted(node_ids)
        return tuple(self._nodes[node_ids[name]] for name in names[offset:])

    def iter_nodes(self) -> Iterable[Node]:
        return tuple(self._nodes.values())
