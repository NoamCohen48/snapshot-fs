"""Human-readable and JSON serialization for CLI inspection output."""

import base64
from datetime import datetime
from typing import Any

from snapshotfs.diagnostics import ImportDiagnostic
from snapshotfs.model import Node
from snapshotfs.model.metadata import thaw_metadata
from snapshotfs.stores.base import SnapshotStore


def print_tree(store: SnapshotStore) -> None:
    snapshot = next(iter(store.iter_nodes())).snapshot_id
    print("/")

    def visit(parent: int, depth: int) -> None:
        for node in store.iter_children(parent):
            suffix = "/" if node.kind.value == "directory" else ""
            print(f"{'  ' * depth}{node.mounted_name.decode('utf-8')}{suffix}")
            if suffix:
                visit(node.id, depth + 1)

    visit(store.get_root(snapshot).id, 1)
    for diagnostic in store.diagnostics:
        print(format_diagnostic(diagnostic))
    if store.diagnostic_count > len(store.diagnostics):
        print(
            f"{store.diagnostic_count} diagnostics observed; "
            f"showing first {len(store.diagnostics)}"
        )


def json_document(store: SnapshotStore) -> dict[str, Any]:
    nodes = list(store.iter_nodes())
    snapshot = store.get_snapshot(nodes[0].snapshot_id)
    return {
        "snapshot": {
            "id": snapshot.id,
            "source_uri": snapshot.source_uri,
            "source_format": snapshot.source_format,
            "imported_at": snapshot.imported_at.isoformat(),
            "source_metadata": thaw_metadata(snapshot.source_metadata),
        },
        "nodes": [_json_node(node) for node in nodes],
        "diagnostics": [
            {
                "severity": item.severity.value,
                "line_number": item.line_number,
                "code": item.code,
                "message": item.message,
            }
            for item in store.diagnostics
        ],
        "diagnostic_count": store.diagnostic_count,
    }


def format_diagnostic(diagnostic: ImportDiagnostic) -> str:
    location = f"line {diagnostic.line_number}: " if diagnostic.line_number else ""
    return (
        f"{diagnostic.severity.value}: {location}{diagnostic.code}: "
        f"{diagnostic.message}"
    )


def _json_node(node: Node) -> dict[str, Any]:
    def timestamp(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    return {
        "id": node.id,
        "parent_id": node.parent_id,
        "mounted_name": node.mounted_name.decode("utf-8"),
        "original_path": node.original_path,
        "kind": node.kind.value,
        "size": node.size,
        "modified_at": timestamp(node.modified_at),
        "content": (
            base64.b64encode(node.content).decode("ascii")
            if node.content is not None
            else None
        ),
        "content_encoding": "base64" if node.content is not None else None,
        "content_status": node.content_status.value,
        "content_ref": node.content_ref,
        "source_line": node.source_line,
        "source_metadata": thaw_metadata(node.source_metadata),
    }
