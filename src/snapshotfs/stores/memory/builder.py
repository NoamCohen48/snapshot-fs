"""Atomic in-memory snapshot builder."""

from collections.abc import Mapping
from types import MappingProxyType

from snapshotfs.diagnostics import ImportDiagnostic
from snapshotfs.model import Node, NodeKind, ParsedEntry, Snapshot
from snapshotfs.stores.building import (
    MutableNode,
    components,
    conflict,
    content_values,
    merge,
)
from snapshotfs.stores.memory.store import InMemorySnapshotStore


class InMemorySnapshotBuilder:
    def __init__(self, snapshot: Snapshot) -> None:
        self._snapshot = snapshot
        self._nodes: dict[int, MutableNode] = {
            1: MutableNode(1, None, b"", None, NodeKind.DIRECTORY)
        }
        self._children: dict[int, dict[bytes, int]] = {1: {}}
        self._next_id = 2
        self._finished = False

    def add(self, entry: ParsedEntry) -> None:
        if self._finished:
            raise RuntimeError("builder is already finished")
        path_components = components(entry)
        parent_id = 1
        for index, mounted_name in enumerate(path_components):
            final = index == len(path_components) - 1
            kind = entry.kind if final else NodeKind.DIRECTORY
            children = self._children.setdefault(parent_id, {})
            existing_id = children.get(mounted_name)
            if existing_id is None:
                node_id = self._next_id
                self._next_id += 1
                node = MutableNode(
                    node_id,
                    parent_id,
                    mounted_name,
                    "/".join(entry.path[: index + 1]),
                    kind,
                )
                self._nodes[node_id] = node
                children[mounted_name] = node_id
                self._children[node_id] = {}
            else:
                node = self._nodes[existing_id]
                if node.kind is not kind:
                    conflict(node, entry, "file/directory type conflict")
            if final:
                merge(node, entry)
            parent_id = node.id

    def finish(
        self,
        diagnostics: tuple[ImportDiagnostic, ...] = (),
        diagnostic_count: int | None = None,
    ) -> "InMemorySnapshotStore":
        if self._finished:
            raise RuntimeError("builder is already finished")
        self._finished = True
        nodes: dict[int, Node] = {}
        exact_children: dict[int, Mapping[bytes, int]] = {}
        for mutable in self._nodes.values():
            content, status = content_values(mutable)
            nodes[mutable.id] = Node(
                mutable.id,
                self._snapshot.id,
                mutable.parent_id,
                mutable.mounted_name,
                mutable.original_path,
                mutable.kind,
                mutable.size,
                mutable.modified_at,
                content,
                status,
                None,
                mutable.source_line,
                MappingProxyType(dict(mutable.source_metadata)),
            )
            child_map = {
                self._nodes[node_id].mounted_name: node_id
                for node_id in self._children.get(mutable.id, {}).values()
            }
            exact_children[mutable.id] = MappingProxyType(child_map)
        return InMemorySnapshotStore(
            self._snapshot,
            MappingProxyType(nodes),
            MappingProxyType(exact_children),
            diagnostics,
            diagnostic_count if diagnostic_count is not None else len(diagnostics),
        )

    def abort(self) -> None:
        self._finished = True
